#ifndef APP_H
#define APP_H

#include <string>

#include <windows.h>

#include "event_queue.h"
#include "webview.h"
#include "window.h"

/* Native host that owns the window and the webview.
 *
 * The window forwards messages here through a static WndProc that recovers
 * the instance from GWLP_USERDATA. Webview construction is asynchronous, so
 * the host navigates once WM_WEBVIEW_RDY reports the core webview is ready
 * and tears the window down once WM_WEBVIEW_CLOSE reports teardown finished.
 * The caller owns the lifecycle: it constructs the host, creates the window,
 * shows it and pumps the message loop.
 */
class App {
public:
	explicit App(std::wstring url);

	App(const App&) = delete;
	App &operator=(const App&) = delete;

	/* Create the top-level window sized to width by height and start
	 * asynchronous webview construction. The window is created hidden; the
	 * caller shows it and runs the message loop.
	 */
	void create(const std::wstring& title, int width, int height);

	HWND hwnd(void) const noexcept { return window_.hwnd(); }
	const Window& window(void) const noexcept { return window_; }
	const WebView& webview(void) const noexcept { return webview_; }

private:
	static LRESULT CALLBACK wnd_proc(HWND, UINT, WPARAM, LPARAM);

	Window window_;
	WebView webview_;
	EventQueue event_q_;
	std::wstring url_;
};

#endif /* APP_H */
