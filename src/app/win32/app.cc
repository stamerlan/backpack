#include "app.h"

#include <format>
#include <utility>

#include "call_q.h"
#include "msg_ids.h"
#include "utf8.h"

LRESULT CALLBACK app_t::wnd_proc(HWND hwnd, UINT m, WPARAM wp, LPARAM lp)
{
	auto *self = reinterpret_cast<app_t *>(
		GetWindowLongPtrW(hwnd, GWLP_USERDATA));
	if (!self)
		return DefWindowProcW(hwnd, m, wp, lp);

	switch (m) {
	case WM_SIZE: {
		RECT r = { 0, 0, LOWORD(lp), HIWORD(lp) };
		self->webview_.resize(r);
		return 0;
	}
	case WM_WEBVIEW_RDY: {
		HRESULT hr = static_cast<HRESULT>(lp);
		if (FAILED(hr)) {
			MessageBoxW(hwnd, std::format(
				L"WebView2 failed to start (0x{:08X})",
				static_cast<unsigned>(hr)).c_str(),
				L"Backpack", MB_OK | MB_ICONERROR);
			DestroyWindow(hwnd);
			return 0;
		}
		self->webview_.navigate(self->url);
		return 0;
	}
	case WM_CLOSE:
		/* Let the webview release its COM objects first, then finish
		 * destruction on WM_WEBVIEW_CLOSE.
		 */
		self->webview_.close();
		return 0;
	case WM_WEBVIEW_CLOSE:
		DestroyWindow(hwnd);
		return 0;
	case WM_CALL:
		call_dispatch(wp);
		return 0;
	case WM_DESTROY:
		PostQuitMessage(0);
		return 0;
	default:
		return DefWindowProcW(hwnd, m, wp, lp);
	}
}

app_t::app_t(HWND hwnd, ATOM atom, std::wstring url)
	: window_(hwnd, atom),
	webview_([this](std::string json) -> HRESULT {
		event_q.push(std::move(json));
		return S_OK;
	}),
	url(std::move(url))
{
	SetWindowLongPtrW(hwnd, GWLP_USERDATA,
		reinterpret_cast<LONG_PTR>(this));
	webview_.create(hwnd, L"");
}

void app_t::eval_js(std::wstring js, ui_queue_t::callback_t cb)
{
	ui_q.push(js, std::move(cb));
	call_later(window_.hwnd(), [this] { ui_q_run(); });
}

void app_t::ui_q_run(void)
{
	for (;;) {
		auto script = ui_q.next();
		if (!script)
			return;

		HRESULT hr = webview_.execute_script(
			*script,
			[this](HRESULT hr, const std::wstring& json) {
				ui_q.complete(hr, json);
				ui_q_run();
			}
		);

		if (SUCCEEDED(hr))
			return;

		/* failed to start script */
		ui_q.complete(hr, {});
	}
}
