#ifndef WEBVIEW_H
#define WEBVIEW_H

#include <functional>
#include <string>
#include <windows.h>
#include <wrl/client.h>
#include <WebView2.h>

class webview_t {
public:
	webview_t(void) = default;
	~webview_t(void) = default;

	webview_t(const webview_t&) = delete;
	webview_t &operator=(const webview_t&) = delete;

	webview_t(webview_t&&) = delete;
	webview_t &operator=(webview_t&&) = delete;

	/* The webview finished building (or failed). */
	std::function<void(HRESULT hr)> on_create;

	/* A message the frontend posted, as a UTF-8 JSON string. */
	std::function<void(std::string json)> on_msg;

	/* A navigation finished. success is false when it failed. */
	std::function<void(bool success)> on_load;

	/* A navigation to uri is about to start. Return true to cancel it. */
	std::function<bool(const std::wstring& uri)> on_nav_start;

	/* The document source (URL) changed to uri. */
	std::function<void(const std::wstring& uri)> on_source_changed;

	/* New content is loading. is_error_page is true for an error page. */
	std::function<void(bool is_error_page)> on_content_loading;

	/* The document title changed to title. */
	std::function<void(const std::wstring& title)> on_title;

	/* The frontend requested a new window for uri (window.open, a
	 * target=_blank link). Return true to mark it handled and suppress
	 * the default new window (e.g. after opening uri elsewhere).
	 */
	std::function<bool(const std::wstring& uri)> on_new_window;

	/* The frontend requested permission of kind for uri. Return the
	 * state to apply (allow, deny, or default).
	 */
	std::function<COREWEBVIEW2_PERMISSION_STATE(
		const std::wstring& uri, COREWEBVIEW2_PERMISSION_KIND kind
	)> on_permission;

	/* A browser process failed with kind (renderer crash, hang, ...). */
	std::function<void(COREWEBVIEW2_PROCESS_FAILED_KIND kind)>
		on_process_failed;

	/* The frontend called window.close(). */
	std::function<void(void)> on_close_requested;

	/* Asynchronously build the WebView2 environment and controller for
	 * parent, storing the browser profile under user_data_dir. Once the
	 * controller and core webview are available (or construction fails)
	 * on_create is invoked from the host message loop.
	 */
	void create(HWND parent, const std::wstring& user_data,
		const std::wstring& assets);

	void navigate(const std::wstring& url) const noexcept;
	void resize(const RECT& r) const noexcept;

	/* Tear down the webview: close the controller and release the COM
	 * objects, then post DestroyWindow(parent) to the host message loop via
	 * call_later() so window destruction runs off this stack. Re-entry during
	 * teardown is ignored.
	 */
	void close(void);

	/* Run one script in the frontend and call cb. Returns the HRESULT of
	 * starting the call: on a success return on_result fires later (from
	 * the UI thread) with the transport HRESULT and the JSON result. On a
	 * failure return the call never started and cb is not invoked. Returns
	 * E_ABORT when the core webview is gone. Must run on the UI thread that
	 * owns the webview.
	 */
	HRESULT execute_script(const std::wstring& script,
		std::function<void(HRESULT, const std::wstring&)> cb);

private:
	HRESULT on_env_created(HRESULT hr, ICoreWebView2Environment *e);
	HRESULT on_ctrl_created(HRESULT hr, ICoreWebView2Controller *c);
	HRESULT on_web_msg_received(
		ICoreWebView2 *sender,
		ICoreWebView2WebMessageReceivedEventArgs *args
	);

	/* Invoke on_create(hr) from the host message loop (via WM_CALL) so it
	 * runs off the WebView2 callback stack and may destroy the window.
	 */
	void post_create(HRESULT hr);

	HWND hwnd = nullptr;
	bool closing = false;
	std::wstring assets_dir;

	Microsoft::WRL::ComPtr<ICoreWebView2Environment> env;
	Microsoft::WRL::ComPtr<ICoreWebView2Controller> ctrl;
	Microsoft::WRL::ComPtr<ICoreWebView2> core;
};

#endif /* WEBVIEW_H */
