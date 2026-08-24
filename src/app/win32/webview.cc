#include "webview.h"
#include <utility>
#include <wrl.h>
#include "msg_ids.h"
#include "utf8.h"

/* Provide the same API as pywebview */
static constexpr wchar_t api[] =
	L"window.pywebview = window.pywebview || {};\n"
	L"window.pywebview.api = window.pywebview.api || {};\n"
	L"window.pywebview.api.dispatch = function (name) {\n"
	L"    var args = Array.prototype.slice.call(arguments, 1);\n"
	L"    window.chrome.webview.postMessage({ name: name, args: args });\n"
	L"};\n";

webview_t::webview_t(std::function<void(std::string json)> web_msg_handler)
	: web_msg_handler(web_msg_handler)
{
}

void webview_t::create(HWND parent_hwnd, const std::wstring& user_data_dir)
{
	hwnd = parent_hwnd;

	const wchar_t *data_dir = user_data_dir.empty()
		? nullptr : user_data_dir.c_str();
	HRESULT hr = CreateCoreWebView2EnvironmentWithOptions(
		nullptr, data_dir, nullptr,
		Microsoft::WRL::Callback<ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler>(
			this, &webview_t::on_env_created
		).Get()
	);
	if (FAILED(hr)) {
		PostMessageW(hwnd, WM_WEBVIEW_RDY,
			reinterpret_cast<WPARAM>(this), static_cast<LPARAM>(hr)
		);
	}
}

void webview_t::navigate(const std::wstring& url) const noexcept
{
	if (core)
		core->Navigate(url.c_str());
}

void webview_t::resize(const RECT& r) const noexcept
{
	if (ctrl)
		ctrl->put_Bounds(r);
}

void webview_t::close(void)
{
	if (closing)
		return;
	closing = true;

	if (ctrl)
		ctrl->Close();

	core.Reset();
	ctrl.Reset();
	env.Reset();

	PostMessageW(hwnd, WM_WEBVIEW_CLOSE, reinterpret_cast<WPARAM>(this), 0);
}

HRESULT webview_t::execute_script(
	const std::wstring& script,
	std::function<void(HRESULT, const std::wstring&)> cb
)
{
	if (!core)
		return E_ABORT;

	return core->ExecuteScript(
		script.c_str(),
		Microsoft::WRL::Callback<ICoreWebView2ExecuteScriptCompletedHandler>(
			[cb = std::move(cb)]
			(HRESULT hr, LPCWSTR json) -> HRESULT {
				std::wstring result;
				if (json)
					result = json;
				cb(hr, result);
				return S_OK;
			}
		).Get());
}

HRESULT webview_t::on_env_created(HRESULT hr, ICoreWebView2Environment *e)
{
	if (FAILED(hr)) {
		PostMessageW(hwnd, WM_WEBVIEW_RDY,
			reinterpret_cast<WPARAM>(this), static_cast<LPARAM>(hr)
		);
		return S_OK;
	}
	env = e;

	hr = env->CreateCoreWebView2Controller(
		hwnd,
		Microsoft::WRL::Callback<ICoreWebView2CreateCoreWebView2ControllerCompletedHandler>(
			this, &webview_t::on_ctrl_created
		).Get()
	);
	if (FAILED(hr))
		PostMessageW(hwnd, WM_WEBVIEW_RDY,
			reinterpret_cast<WPARAM>(this), static_cast<LPARAM>(hr)
		);
	return S_OK;
}

HRESULT webview_t::on_ctrl_created(HRESULT hr, ICoreWebView2Controller *c)
{
	if (FAILED(hr)) {
		PostMessageW(hwnd, WM_WEBVIEW_RDY,
			reinterpret_cast<WPARAM>(this), static_cast<LPARAM>(hr)
		);
		return S_OK;
	}

	ctrl = c;

	hr = ctrl->get_CoreWebView2(&core);
	if (FAILED(hr)) {
		PostMessageW(hwnd, WM_WEBVIEW_RDY,
			reinterpret_cast<WPARAM>(this), static_cast<LPARAM>(hr)
		);
		return S_OK;
	}

	EventRegistrationToken token;
	core->add_WebMessageReceived(
		Microsoft::WRL::Callback<ICoreWebView2WebMessageReceivedEventHandler>(
			this, &webview_t::on_web_msg_received
		).Get(),
		&token
	);

	core->AddScriptToExecuteOnDocumentCreated(api,
		Microsoft::WRL::Callback<ICoreWebView2AddScriptToExecuteOnDocumentCreatedCompletedHandler>(
			[](HRESULT, LPCWSTR) -> HRESULT { return S_OK; }
		).Get()
	);

	RECT bounds = {};
	GetClientRect(hwnd, &bounds);
	ctrl->put_Bounds(bounds);

	PostMessageW(
		hwnd, WM_WEBVIEW_RDY,
		reinterpret_cast<WPARAM>(this), static_cast<LPARAM>(hr)
	);
	return S_OK;
}

HRESULT webview_t::on_web_msg_received(
	ICoreWebView2 *sender,
	ICoreWebView2WebMessageReceivedEventArgs *args)
{
	(void)sender;

	if (!args)
		return S_OK;

	try {
		LPWSTR msg = nullptr;
		if (FAILED(args->get_WebMessageAsJson(&msg)) || !msg)
			return S_OK;
		std::string json = wstr_to_utf8(msg);
		CoTaskMemFree(msg);

		web_msg_handler(json);
	} catch (...) {}

	return S_OK;
}
