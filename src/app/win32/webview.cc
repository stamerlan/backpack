#include "webview.h"
#include <utility>
#include <nlohmann/json.hpp>
#include <wrl.h>
#include "msg_ids.h"
#include "utf8.h"

using Microsoft::WRL::Callback;

using env_cpl_cb = ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler;
using ctrl_cpl_cb = ICoreWebView2CreateCoreWebView2ControllerCompletedHandler;

/* Provide the same API as pywebview */
static constexpr wchar_t api[] =
	L"window.pywebview = window.pywebview || {};\n"
	L"window.pywebview.api = window.pywebview.api || {};\n"
	L"window.pywebview.api.dispatch = function (name) {\n"
	L"    var args = Array.prototype.slice.call(arguments, 1);\n"
	L"    window.chrome.webview.postMessage({ name: name, args: args });\n"
	L"};\n";

void WebView::create(HWND parent_hwnd, const std::wstring& user_data_dir,
	EventQueue *events)
{
	hwnd_ = parent_hwnd;
	event_q_ = events;

	const wchar_t *data_dir = user_data_dir.empty()
		? nullptr : user_data_dir.c_str();

	HRESULT hr = CreateCoreWebView2EnvironmentWithOptions(
		nullptr, data_dir, nullptr,
		Callback<env_cpl_cb>(this, &WebView::on_env_created).Get()
	);
	if (FAILED(hr))
		PostMessageW(hwnd_, WM_WEBVIEW_RDY,
			reinterpret_cast<WPARAM>(this), static_cast<LPARAM>(hr)
		);
}

void WebView::navigate(const std::wstring& url) const noexcept
{
	if (core_)
		core_->Navigate(url.c_str());
}

void WebView::resize(const RECT& r) const noexcept
{
	if (ctrl_)
		ctrl_->put_Bounds(r);
}

void WebView::close(void)
{
	if (closing_)
		return;
	closing_ = true;

	if (ctrl_)
		ctrl_->Close();

	core_.Reset();
	ctrl_.Reset();
	env_.Reset();

	PostMessageW(hwnd_, WM_WEBVIEW_CLOSE, reinterpret_cast<WPARAM>(this),
		0);
}

void WebView::eval_js(std::wstring js, JsQueue::Callback cb)
{
	js_q_.push(js, std::move(cb));
	PostMessageW(hwnd_, WM_JS_RUN, reinterpret_cast<WPARAM>(this), 0);
}

void WebView::process_js_q(void)
{
	js_q_.process(core_);
}

HRESULT WebView::on_env_created(HRESULT hr, ICoreWebView2Environment *env)
{
	if (FAILED(hr)) {
		PostMessageW(hwnd_, WM_WEBVIEW_RDY,
			reinterpret_cast<WPARAM>(this), static_cast<LPARAM>(hr)
		);
		return S_OK;
	}

	env_ = env;
	hr = env_->CreateCoreWebView2Controller(
		hwnd_,
		Callback<ctrl_cpl_cb>(this, &WebView::on_ctrl_created).Get()
	);
	if (FAILED(hr))
		PostMessageW(hwnd_, WM_WEBVIEW_RDY,
			reinterpret_cast<WPARAM>(this), static_cast<LPARAM>(hr)
		);
	return S_OK;
}

HRESULT WebView::on_ctrl_created(HRESULT hr, ICoreWebView2Controller *ctrl)
{
	if (FAILED(hr)) {
		PostMessageW(hwnd_, WM_WEBVIEW_RDY,
			reinterpret_cast<WPARAM>(this), static_cast<LPARAM>(hr)
		);
		return S_OK;
	}

	ctrl_ = ctrl;
	hr = ctrl_->get_CoreWebView2(&core_);
	if (FAILED(hr)) {
		PostMessageW(hwnd_, WM_WEBVIEW_RDY,
			reinterpret_cast<WPARAM>(this), static_cast<LPARAM>(hr)
		);
		return S_OK;
	}

	EventRegistrationToken msg_token;
	auto msg_cb = Callback<ICoreWebView2WebMessageReceivedEventHandler>(
		[this](
			ICoreWebView2 *,
			ICoreWebView2WebMessageReceivedEventArgs *args
		) -> HRESULT {
			on_web_message(args);
			return S_OK;
		}
	);
	core_->add_WebMessageReceived(msg_cb.Get(), &msg_token);

	auto add_script_cb =
		Callback<ICoreWebView2AddScriptToExecuteOnDocumentCreatedCompletedHandler>(
			[](HRESULT, LPCWSTR) -> HRESULT { return S_OK; }
		);
	core_->AddScriptToExecuteOnDocumentCreated(api, add_script_cb.Get());

	RECT bounds = {};
	GetClientRect(hwnd_, &bounds);
	ctrl_->put_Bounds(bounds);

	PostMessageW(hwnd_, WM_WEBVIEW_RDY,
		reinterpret_cast<WPARAM>(this), static_cast<LPARAM>(hr)
	);
	return S_OK;
}

void WebView::on_web_message(ICoreWebView2WebMessageReceivedEventArgs *args)
{
	if (!event_q_ || !args)
		return;

	LPWSTR msg = nullptr;
	if (FAILED(args->get_WebMessageAsJson(&msg)) || !msg)
		return;
	std::string json = wstr_to_utf8(msg);
	CoTaskMemFree(msg);

	nlohmann::json doc = nlohmann::json::parse(json, nullptr, false);
	if (!doc.is_object() ||
	    !doc.contains("name") || !doc["name"].is_string())
		return;

	EventQueue::Event event;
	event.name = doc["name"].get<std::string>();
	event.args = doc.contains("args") && doc["args"].is_array()
		? doc["args"].dump() : "[]";
	event_q_->post(std::move(event));
}
