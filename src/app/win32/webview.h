#ifndef WEBVIEW_H
#define WEBVIEW_H

#include <string>
#include <windows.h>
#include <wrl/client.h>
#include <WebView2.h>

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
	 * success the controller is sized to the parent client rect.
	 */
	void create(HWND parent, const std::wstring& user_data_dir);

private:
	HRESULT on_env_created(HRESULT hr, ICoreWebView2Environment *env);
	HRESULT on_ctrl_created(HRESULT hr, ICoreWebView2Controller *ctrl);

	HWND hwnd_ = nullptr;
	Microsoft::WRL::ComPtr<ICoreWebView2Environment> env_;
	Microsoft::WRL::ComPtr<ICoreWebView2Controller> ctrl_;
	Microsoft::WRL::ComPtr<ICoreWebView2> core_;
};

#endif /* WEBVIEW_H */
