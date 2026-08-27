#ifndef APP_H
#define APP_H

#include <string>

#include <windows.h>

#include "webview.h"
#include "window.h"

class app_t {
public:
	app_t(HWND hwnd, ATOM atom, std::wstring url);

	app_t(const app_t&) = delete;
	app_t &operator=(const app_t&) = delete;

	static LRESULT CALLBACK wnd_proc(HWND, UINT, WPARAM, LPARAM);

	HWND hwnd(void) const noexcept { return window_.hwnd(); }
	const window_t& window(void) const noexcept { return window_; }
	const webview_t& webview(void) const noexcept { return webview_; }

private:
	window_t window_;
	webview_t webview_;
	std::wstring url;
};

#endif /* APP_H */
