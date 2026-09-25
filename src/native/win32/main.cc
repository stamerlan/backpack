#include <exception>
#include <format>
#include <memory>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>
#include <utility>

#include <windows.h>
#include <objbase.h>
#include <shellapi.h>

#include <Python.h>

#include "defer_call.h"
#include "event_queue.h"
#include "py/config.h"
#include "script_queue.h"
#include "utf8.h"
#include "webview.h"
#include "window.h"
#include "winerr.h"

struct app_t {
	window_t window;
	webview_t webview;
	event_queue_t event_q;
	script_queue_t script_q;
	std::wstring url;

	app_t(HWND hwnd, ATOM atom, std::wstring url, std::wstring assets);
	~app_t(void);
};

using py_ref = std::unique_ptr<PyObject, decltype(&Py_DecRef)>;

static std::wstring get_module_dir(void)
{
	std::wstring path(MAX_PATH, L'\0');
	for (;;) {
		DWORD path_size = static_cast<DWORD>(path.size());
		DWORD n = GetModuleFileNameW(nullptr, path.data(), path_size);
		if (n == 0)
			throw win32_error("GetModuleFileNameW() failed");
		if (n < path_size) {
			path.resize(n);
			break;
		}
		path.resize(path_size * 2);
	}
	size_t slash = path.find_last_of(L"\\/");
	if (slash != std::wstring::npos)
		path.resize(slash);
	return path;
}

/* Take the raised Python exception and return it as "Type: message".
 * The caller must hold GIL.
 */
static std::string get_py_exception(void)
{
	PyObject *exc = PyErr_GetRaisedException();
	if (!exc)
		return "unknown Python error";
	std::string msg = Py_TYPE(exc)->tp_name;
	if (PyObject *s = PyObject_Str(exc)) {
		if (const char *u = PyUnicode_AsUTF8(s)) {
			if (*u) {
				msg += ": ";
				msg += u;
			}
		}
		Py_DECREF(s);
	}
	PyErr_Clear();
	Py_DECREF(exc);
	return msg;
}

static LRESULT CALLBACK wnd_proc(HWND hwnd, UINT m, WPARAM wp, LPARAM lp)
{
	auto *self = reinterpret_cast<app_t *>(
		GetWindowLongPtrW(hwnd, GWLP_USERDATA));
	if (!self)
		return DefWindowProcW(hwnd, m, wp, lp);

	switch (m) {
	case WM_SIZE: {
		RECT r = { 0, 0, LOWORD(lp), HIWORD(lp) };
		self->webview.resize(r);
		return 0;
	}
	case WM_CLOSE:
		/* Hand the close attempt to Core as an event and keep the
		 * window open: python core runs its shutdown and closes the
		 * webview when it is done. The window itself is destroyed
		 * by wWinMain once Core is gone.
		 */
		self->event_q.push("{ \"name\": \"close\", \"args\": [] }");
		return 0;
	case WM_APP:
		defer_call_run(wp);
		return 0;
	case WM_SETTINGCHANGE:
		/* Apply system theme, just in case it's changed */
		if (self->window.is_system_theme())
			self->window.set_theme(L"system");
		return 0;
	default:
		return DefWindowProcW(hwnd, m, wp, lp);
	}
}

app_t::app_t(HWND hwnd, ATOM atom, std::wstring url, std::wstring assets)
	: window(hwnd, atom),
	script_q(hwnd, webview),
	url(std::move(url))
{
	SetWindowLongPtrW(hwnd, GWLP_USERDATA,
		reinterpret_cast<LONG_PTR>(this));
	webview.on_create = [this, hwnd](HRESULT hr) {
		if (FAILED(hr)) {
			MessageBoxW(hwnd, std::format(
				L"WebView2 failed to start (0x{:08X})",
				static_cast<unsigned>(hr)).c_str(),
				L"Backpack", MB_OK | MB_ICONERROR);
			webview.close();
			return;
		}
		webview.navigate(this->url);
	};
	webview.on_closed = [this] {
		script_q.abort();
		event_q.abort();
	};
	webview.on_msg = [this](std::string json) {
		event_q.push(std::move(json));
	};
	webview.on_load = [this](bool, COREWEBVIEW2_WEB_ERROR_STATUS, int) {
		event_q.push("{ \"name\": \"load\", \"args\": [] }");
	};
	webview.create(hwnd, L"", assets);
}

app_t::~app_t(void)
{
	SetWindowLongPtrW(window.hwnd(), GWLP_USERDATA, 0);
}

/* Build the Windows app host (native.win32.WinAppHost) that Core drives,
 * injecting the Python objects over the native window, webview and queues.
 * Returns a new reference, or nullptr with a Python error set.
 */
static PyObject *build_py_app(app_t& app)
{
	py_ref window(app.window.to_py(), Py_DecRef);
	if (!window)
		return nullptr;
	py_ref webview(app.webview.to_py(), Py_DecRef);
	if (!webview)
		return nullptr;
	py_ref event_q(app.event_q.to_py(), Py_DecRef);
	if (!event_q)
		return nullptr;
	py_ref script_q(app.script_q.to_py(), Py_DecRef);
	if (!script_q)
		return nullptr;

	PyObject *mod = PyImport_ImportModule("native.win32");
	if (!mod)
		return nullptr;

	PyObject *cls = PyObject_GetAttrString(mod, "WinAppHost");
	Py_DECREF(mod);

	if (!cls)
		return nullptr;

	PyObject *py_app = PyObject_CallFunctionObjArgs(
		cls, window.get(), webview.get(), event_q.get(), script_q.get(),
		nullptr);
	Py_DECREF(cls);

	return py_app;
}

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int)
try {
	HRESULT hr = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
	if (FAILED(hr))
		throw win32_error(hr, "CoInitializeEx() failed");

	static const wchar_t *const wnd_class = L"BackpackWindow";
	HINSTANCE hinst = GetModuleHandleW(nullptr);

	WNDCLASSEXW wc = {};
	wc.cbSize = sizeof(wc);
	wc.style = CS_HREDRAW | CS_VREDRAW;
	wc.lpfnWndProc = wnd_proc;
	wc.hInstance = hinst;
	wc.hCursor = LoadCursorW(nullptr, IDC_ARROW);
	wc.lpszClassName = wnd_class;

	ATOM atom = RegisterClassExW(&wc);
	if (atom == 0)
		throw win32_error("RegisterClassExW() failed");

	RECT rect = { 0, 0, 1200, 800 };
	AdjustWindowRectEx(&rect, WS_OVERLAPPEDWINDOW, FALSE, 0);

	HWND hwnd = CreateWindowExW(
		0, wnd_class, L"Backpack", WS_OVERLAPPEDWINDOW,
		CW_USEDEFAULT, CW_USEDEFAULT,
		rect.right - rect.left, rect.bottom - rect.top,
		nullptr, nullptr, hinst, nullptr);
	if (!hwnd)
		throw win32_error("CreateWindowExW() failed");

	int argc = 0;
	std::unique_ptr<LPWSTR, decltype(&LocalFree)> argv(
		CommandLineToArgvW(GetCommandLineW(), &argc), &LocalFree);
	if (!argv)
		argc = 0;

	/* --dev [URL] loads the UI from a Vite dev server instead of assets */
	std::wstring url = L"https://assets/index.html";
	for (int i = 1; i < argc; i++) {
		if (std::wstring_view(argv.get()[i]) != L"--dev")
			continue;
		url = L"http://localhost:5173";
		if (i + 1 < argc && argv.get()[i + 1][0] != L'-')
			url = argv.get()[i + 1];
	}

	std::wstring app_dir = get_module_dir();
	std::wstring assets_dir = app_dir + L"\\assets";

	app_t app(hwnd, atom, url, assets_dir);
	app.window.set_theme(L"system");
	app.window.show();

	py::config_t config;
	config.set_parse_argv(0);
	config.set_program_name((app_dir + L"\\backpack.exe").c_str());
	config.set_home(app_dir.c_str());
	config.add_module_search_path((app_dir + L"\\lib").c_str());
	if (argv)
		config.set_argv(argc, argv.get());
	config.init();

	/* Imports and backpack.main run on the core thread, so the UI thread
	 * keeps pumping messages and WebView2 starts in parallel. Release the
	 * GIL for it; the UI thread re-takes it inside bridge callbacks.
	 */
	PyThreadState *main_th_state = PyEval_SaveThread();

	std::exception_ptr core_exc;
	std::thread core_thread([&app, &core_exc] {
		PyGILState_STATE gil = PyGILState_Ensure();
		try {
			py_ref pyapp(build_py_app(app), Py_DecRef);
			if (!pyapp)
				throw std::runtime_error(get_py_exception());

			PyObject *core = PyImport_ImportModule("backpack");
			if (core) {
				PyObject *r = PyObject_CallMethod(
					core, "main", "O", pyapp.get());
				if (!r)
					PyErr_Print();
				else
					Py_DECREF(r);
				Py_DECREF(core);
			} else {
				PyErr_Print();
			}
		} catch (...) {
			core_exc = std::current_exception();
		}
		PyGILState_Release(gil);
	});

	/* Process messages while python thread is running */
	HANDLE core_handle = core_thread.native_handle();
	for (;;) {
		DWORD r = MsgWaitForMultipleObjectsEx(1, &core_handle,
			INFINITE, QS_ALLINPUT, MWMO_INPUTAVAILABLE);
		if (r != WAIT_OBJECT_0 + 1)
			break;
		MSG m;
		while (PeekMessageW(&m, nullptr, 0, 0, PM_REMOVE)) {
			TranslateMessage(&m);
			DispatchMessageW(&m);
		}
	}
	core_thread.join();

	/* Python core is finished. Close the webview just in cases python core
	 * haven't done it yet. Abort queues to release resources held by
	 * callbacks. Destroy window.
	 */
	app.webview.close();
	defer_call_cancel();
	DestroyWindow(hwnd);

	PyEval_RestoreThread(main_th_state);
	Py_Finalize();

	CoUninitialize();

	if (core_exc)
		std::rethrow_exception(core_exc);
	return 0;
} catch (const PyStatus& status) {
	std::wstring msg(L"Python error");
	if (status.err_msg) {
		msg += L"\n\n";
		msg += utf8_to_wstr(status.err_msg);
	}
	MessageBoxW(nullptr, msg.c_str(), L"Backpack", MB_OK | MB_ICONERROR);
	return 1;
} catch (const std::exception& e) {
	MessageBoxW(nullptr, utf8_to_wstr(e.what()).c_str(),
		L"Backpack", MB_OK | MB_ICONERROR);
	return 1;
}
