#include <Python.h>

#include <string>
#include <thread>

#include <windows.h>
#include <objbase.h>
#include <shellapi.h>

#include "app.h"
#include "call_q.h"
#include "pyconfig.h"
#include "pyext.h"
#include "utf8.h"
#include "winerr.h"

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

/* Start the embedded interpreter against the bundled runtime.
 *
 * The bundle keeps the standard library and every third-party module under
 * <app_dir>/lib, so the search path is set to exactly that and the default
 * path calculation is skipped. The real command line is passed through so
 * core still sees flags such as --dev and --debug.
 */
static void init_python(const std::wstring& app_dir)
{
	py::Config cfg;
	std::wstring exe = app_dir + L"\\backpack.exe";
	cfg.set_program_name(exe.c_str());
	cfg.set_home(app_dir.c_str());
	cfg.add_module_search_path((app_dir + L"\\lib").c_str());

	int argc = 0;
	LPWSTR *argv = CommandLineToArgvW(GetCommandLineW(), &argc);
	if (argv) {
		cfg.set_argv(argc, argv);
		LocalFree(argv);
	}
	cfg.init();
}

/* Build the Windows App host (app.win32.WinApp) that Core drives. It wraps
 * the _app primitives, which forward to the native host set above. Returns a
 * new reference, or nullptr with a Python error set.
 */
static PyObject *build_py_app(void)
{
	PyObject *mod = PyImport_ImportModule("app.win32");
	if (!mod)
		return nullptr;
	PyObject *cls = PyObject_GetAttrString(mod, "WinApp");
	Py_DECREF(mod);
	if (!cls)
		return nullptr;
	PyObject *obj = PyObject_CallNoArgs(cls);
	Py_DECREF(cls);
	return obj;
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
	wc.lpfnWndProc = app_t::wnd_proc;
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

	std::wstring app_dir = get_module_dir();
	std::wstring assets_dir = app_dir + L"\\assets";
	std::wstring url = std::wstring(L"https://") +
		webview_t::asset_host() + L"/index.html";

	app_t app(hwnd, atom, url, assets_dir);

	/* The _app extension forwards every call to this host, so wire it up
	 * and register the builtin before the interpreter starts.
	 */
	pyext_set_app(&app);
	if (PyImport_AppendInittab("_app", &pyext_init) != 0)
		throw std::runtime_error("PyImport_AppendInittab(_app) failed");

	init_python(app_dir);

	PyObject *pyapp = build_py_app();
	if (!pyapp) {
		PyErr_Print();
		throw std::runtime_error("could not build the Python app host");
	}

	app.window().show();

	/* core.main owns the asyncio loop and blocks until Core's lifecycle
	 * ends. Release the GIL so the core thread runs; the UI thread only
	 * pumps messages and re-takes the GIL inside bridge callbacks.
	 */
	PyThreadState *main_ts = PyEval_SaveThread();

	std::thread core_thread([&app, pyapp] {
		PyGILState_STATE gil = PyGILState_Ensure();
		PyObject *core = PyImport_ImportModule("core");
		if (core) {
			PyObject *r = PyObject_CallMethod(core, "main", "O",
				pyapp);
			if (!r)
				PyErr_Print();
			else
				Py_DECREF(r);
			Py_DECREF(core);
		} else {
			PyErr_Print();
		}
		PyGILState_Release(gil);

		/* Whatever ended Core, tear the GUI down so the pump exits.
		 * On a normal shutdown Core already posted this; the second
		 * post is a harmless no-op once the window is gone.
		 */
		app.quit();
	});

	MSG m = {};
	while (GetMessageW(&m, nullptr, 0, 0) > 0) {
		TranslateMessage(&m);
		DispatchMessageW(&m);
	}
	call_cancel();

	/* The GUI ended. If Core is still waiting on an event, unblock it so
	 * core.main unwinds, then join the core thread.
	 */
	{
		PyGILState_STATE gil = PyGILState_Ensure();
		PyObject *r = PyObject_CallMethod(pyapp, "_abort", nullptr);
		if (!r)
			PyErr_Print();
		else
			Py_DECREF(r);
		PyGILState_Release(gil);
	}
	core_thread.join();

	PyEval_RestoreThread(main_ts);
	Py_DECREF(pyapp);
	Py_Finalize();

	CoUninitialize();
	return static_cast<int>(m.wParam);
} catch (const std::exception& e) {
	MessageBoxW(nullptr, utf8_to_wstr(e.what()).c_str(), L"Backpack",
		MB_OK | MB_ICONERROR);
	return 1;
} catch (...) {
	MessageBoxW(nullptr, L"Backpack failed to start", L"Backpack",
		MB_OK | MB_ICONERROR);
	return 1;
}
