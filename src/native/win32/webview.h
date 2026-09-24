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

	/* The webview is created. */
	std::function<void(HRESULT hr)> on_create;

	/* A message the frontend posted, as a UTF-8 JSON object. */
	std::function<void(std::string json)> on_msg;

	/* A navigation finished. ok is false when it failed; web_error is the
	 * failure reason (COREWEBVIEW2_WEB_ERROR_STATUS_UNKNOWN on success) and
	 * http_status the HTTP status code (0 when unavailable).
	 */
	std::function<void(bool ok, COREWEBVIEW2_WEB_ERROR_STATUS web_error,
		int http_status)> on_load;

	/* The document title changed to title. */
	std::function<void(const std::wstring& title)> on_title;

	/* A browser process failed with kind (renderer crash, hang, ...).
	 * reason is the more specific reason
	 * (COREWEBVIEW2_PROCESS_FAILED_REASON_UNEXPECTED when unavailable) and
	 * exit_code the process exit code (0 when unavailable).
	 */
	std::function<void(COREWEBVIEW2_PROCESS_FAILED_KIND kind,
		COREWEBVIEW2_PROCESS_FAILED_REASON reason, int exit_code)>
		on_process_failed;

	/* The frontend called window.close(). */
	std::function<void(void)> on_close_requested;

	/* The webview is closed (close() ran). */
	std::function<void(void)> on_closed;

	/* Asynchronously build the WebView2 environment and controller for
	 * parent, storing the browser profile under user_data_dir. Once the
	 * controller and core webview are available (or construction fails)
	 * on_create is invoked from the host message loop.
	 */
	void create(HWND parent, const std::wstring& user_data,
		const std::wstring& assets);

	void navigate(const std::wstring& url) const noexcept;
	void resize(const RECT& r) const noexcept;

	/* Tear down the webview: close the controller, release the COM objects,
	 * hide the parent window and fire on_closed. The parent window is left
	 * to its owner to destroy. Calls after the first are ignored.
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

	HWND hwnd = nullptr;
	bool closed = false;
	std::wstring assets_dir;

	Microsoft::WRL::ComPtr<ICoreWebView2Environment> env;
	Microsoft::WRL::ComPtr<ICoreWebView2Controller> ctrl;
	Microsoft::WRL::ComPtr<ICoreWebView2> core;
};

#endif /* WEBVIEW_H */
