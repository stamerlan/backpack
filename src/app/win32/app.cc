#include "app.h"

#include <format>
#include <utility>

#include "msg_ids.h"

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
	case WM_DESTROY:
		PostQuitMessage(0);
		return 0;
	default:
		return DefWindowProcW(hwnd, m, wp, lp);
	}
}

app_t::app_t(HWND hwnd, ATOM atom, std::wstring url)
	: window_(hwnd, atom),
	webview_([](std::string json) -> HRESULT { (void)json; return S_OK; }),
	url(std::move(url))
{
	SetWindowLongPtrW(hwnd, GWLP_USERDATA,
		reinterpret_cast<LONG_PTR>(this));
	webview_.create(hwnd, L"");
}
