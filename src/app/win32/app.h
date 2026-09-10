#ifndef APP_H
#define APP_H

#include <functional>
#include <mutex>
#include <optional>
#include <string>
#include <vector>

#include <windows.h>

#include "dialog.h"
#include "event_queue.h"
#include "ui_queue.h"
#include "webview.h"
#include "window.h"

class app_t {
public:
	/* Adopt the already-created top-level window (and its class atom) and
	 * start asynchronous webview construction. url is the address to
	 * navigate to; assets, when non-empty, is mapped to the WebView asset
	 * host so a bundled frontend loads over a real origin. wWinMain
	 * registers the class and creates the window with wnd_proc, then hands
	 * both here. See webview_t::create.
	 */
	app_t(HWND hwnd, ATOM atom, std::wstring url, std::wstring assets);

	app_t(const app_t&) = delete;
	app_t &operator=(const app_t&) = delete;

	static LRESULT CALLBACK wnd_proc(HWND, UINT, WPARAM, LPARAM);

	HWND hwnd(void) const noexcept { return window_.hwnd(); }
	const window_t& window(void) const noexcept { return window_; }
	const webview_t& webview(void) const noexcept { return webview_; }

	/* Schedule a script to run in the frontend.
	 *
	 * Thread safe. One script is run at a time.
	 */
	void eval_js(std::wstring js, ui_queue_t::callback_t cb);

	/* Request application teardown. Thread safe: called from the core
	 * thread when Core's lifecycle ends. Window destruction must run on
	 * the UI thread that owns the window, so this only posts WM_APP_QUIT
	 * and the pump releases the webview and destroys it. Safe to call after
	 * the window has already gone.
	 */
	void quit(void) const noexcept;

	/* Register a callback for the next inbound event: a frontend call or an
	 * OS load/close notice. Thread safe. cb fires with a queued event right
	 * away, or once the next one arrives. Returns false without registering
	 * when the event bridge is shut down. See event_queue_t::get.
	 */
	bool get_event(std::function<void(std::string)> cb);

	/* Window operations. Thread safe: they are queued and run on the UI
	 * thread so the core thread never blocks on the window's message pump.
	 */
	void set_title(std::wstring title);
	void hide(void);
	void set_theme(std::wstring mode);

	/* Show a native open dialog on the UI thread. Thread safe; cb settles
	 * with the picked paths, empty on cancel. See dialog_t::show_open.
	 */
	void show_open_dialog(bool multiple,
		std::vector<std::pair<std::wstring, std::wstring>> filters,
		std::function<void(dialog_t::result_t)> cb);

	/* Show a native save dialog on the UI thread. Thread safe; cb settles
	 * with the chosen path, empty on cancel. See dialog_t::show_save.
	 */
	void show_save_dialog(std::wstring filename,
		std::vector<std::pair<std::wstring, std::wstring>> filters,
		std::function<void(dialog_t::result_t)> cb);

private:
	void ui_q_run(void);

	/* Show d on the UI thread and settle cb with its result. Rejects cb
	 * with an error when a dialog is already open - only one shows at a
	 * time. Thread safe.
	 */
	void show_dialog(dialog_t d,
		std::function<void(dialog_t::result_t)> cb);

	window_t window_;
	webview_t webview_;
	ui_queue_t ui_q;
	event_queue_t event_q;
	std::mutex dialog_m_;
	std::optional<dialog_t> dialog_;

	/* Guards theme, re-applied on WM_SETTINGCHANGE. */
	std::mutex theme_m_;
	std::wstring theme;

	std::wstring url;
};

#endif /* APP_H */
