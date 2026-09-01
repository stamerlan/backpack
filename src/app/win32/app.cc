#include "app.h"

#include <format>
#include <utility>

#include "msg_ids.h"

LRESULT CALLBACK App::wnd_proc(HWND hwnd, UINT m, WPARAM wp, LPARAM lp)
{
	if (m == WM_NCCREATE) {
		auto *cs = reinterpret_cast<CREATESTRUCTW *>(lp);
		SetWindowLongPtrW(hwnd, GWLP_USERDATA,
			reinterpret_cast<LONG_PTR>(cs->lpCreateParams));
		return DefWindowProcW(hwnd, m, wp, lp);
	}

	auto *self = reinterpret_cast<App *>(
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
		self->webview_.navigate(self->url_);
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
	case WM_JS_RUN:
		self->webview_.process_js_q();
		return 0;
	case WM_DESTROY:
		PostQuitMessage(0);
		return 0;
	default:
		return DefWindowProcW(hwnd, m, wp, lp);
	}
}

App::App(std::wstring url) : url_(std::move(url))
{
}

void App::create(const std::wstring& title, int width, int height)
{
	window_.create(title, width, height, &App::wnd_proc, this);
	webview_.create(window_.hwnd(), L"");
}
