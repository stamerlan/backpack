#ifndef WEBVIEW_H
#define WEBVIEW_H

#include <string>
#include <windows.h>
#include <wrl/client.h>
#include <WebView2.h>

#include "event_queue.h"
#include "js_queue.h"

class WebView {
public:
	WebView(void) = default;
	~WebView(void) = default;

	WebView(const WebView&) = delete;
	WebView &operator=(const WebView&) = delete;

	/* Asynchronously build the WebView2 environment and controller for
	 * parent, storing the browser profile under user_data_dir. Once the
	 * controller and core webview are available (or construction fails) a
	 * WM_WEBVIEW_RDY message is posted to parent, so the completion runs
	 * from the host message loop instead of the WebView2 callback. On
	 * success the controller is sized to the parent client rect and the
	 * frontend web-message channel is wired to events (as
	 * window.pywebview.api for compatibility with pywebview).
	 */
	void create(HWND parent, const std::wstring& user_data_dir,
		EventQueue *events);

	/* Navigate the core webview to url. No-op until the core webview is
	 * ready, since construction is asynchronous.
	 */
	void navigate(const std::wstring& url) const noexcept;

	/* Size the controller to r. No-op until the controller is ready. */
	void resize(const RECT& r) const noexcept;

	/* Tear down the webview: close the controller and release the COM
	 * objects, then post WM_WEBVIEW_CLOSE to parent so the host can finish
	 * window destruction from its message loop. Re-entry during teardown is
	 * ignored.
	 */
	void close(void);

	/* Schedule a script execution.
	 *
	 * Thread safe. Calls serialize, one in flight at a time, so cb fires in
	 * submission order and the next call starts only once the prior one
	 * settles.
	 */
	void eval_js(std::wstring js, JsQueue::Callback cb);

	/* Run the next queued script on the UI thread. Posted via WM_JS_RUN. */
	void process_js_q(void);

private:
	HRESULT on_env_created(HRESULT hr, ICoreWebView2Environment *env);
	HRESULT on_ctrl_created(HRESULT hr, ICoreWebView2Controller *ctrl);
	void on_web_message(ICoreWebView2WebMessageReceivedEventArgs *args);

	HWND hwnd_ = nullptr;
	bool closing_ = false;
	EventQueue *event_q_ = nullptr;
	Microsoft::WRL::ComPtr<ICoreWebView2Environment> env_;
	Microsoft::WRL::ComPtr<ICoreWebView2Controller> ctrl_;
	Microsoft::WRL::ComPtr<ICoreWebView2> core_;
	JsQueue js_q_;
};

#endif /* WEBVIEW_H */
