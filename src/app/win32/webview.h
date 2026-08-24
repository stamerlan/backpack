#ifndef WEBVIEW_H
#define WEBVIEW_H

#include <functional>
#include <string>
#include <windows.h>
#include <wrl/client.h>
#include <WebView2.h>

class webview_t {
public:
	webview_t(std::function<void(std::string json)> web_msg_handler);
	~webview_t(void) = default;

	webview_t(const webview_t&) = delete;
	webview_t &operator=(const webview_t&) = delete;

	/* Asynchronously build the WebView2 environment and controller for
	 * parent, storing the browser profile under user_data_dir. Once the
	 * controller and core webview are available (or construction fails) a
	 * WM_WEBVIEW_RDY message is posted to parent, so the completion runs
	 * from the host message loop instead of the WebView2 callback. On
	 * success the controller is sized to the parent client rect.
	 */
	void create(HWND parent, const std::wstring& user_data_dir);

	void navigate(const std::wstring& url) const noexcept;
	void resize(const RECT& r) const noexcept;

	/* Tear down the webview: close the controller and release the COM
	 * objects, then post WM_WEBVIEW_CLOSE to parent so the host can finish
	 * window destruction from its message loop. Re-entry during teardown is
	 * ignored.
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
	bool closing = false;
	std::function<void(std::string json)> web_msg_handler;

	Microsoft::WRL::ComPtr<ICoreWebView2Environment> env;
	Microsoft::WRL::ComPtr<ICoreWebView2Controller> ctrl;
	Microsoft::WRL::ComPtr<ICoreWebView2> core;
};

#endif /* WEBVIEW_H */
