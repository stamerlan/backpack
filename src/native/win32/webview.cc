#include "webview.h"
#include <utility>
#include <wrl.h>
#include "defer_call.h"
#include "utf8.h"

/* Provide the same API as pywebview */
static constexpr wchar_t api[] =
	L"window.pywebview = window.pywebview || {};\n"
	L"window.pywebview.api = window.pywebview.api || {};\n"
	L"window.pywebview.api.dispatch = function (name) {\n"
	L"    var args = Array.prototype.slice.call(arguments, 1);\n"
	L"    window.chrome.webview.postMessage({ name: name, args: args });\n"
	L"};\n";

void webview_t::create(HWND parent_hwnd, const std::wstring& user_data,
	const std::wstring& assets)
{
	hwnd = parent_hwnd;
	assets_dir = assets;

	const wchar_t *data_dir = user_data.empty()
		? nullptr : user_data.c_str();
	HRESULT hr = CreateCoreWebView2EnvironmentWithOptions(
		nullptr, data_dir, nullptr,
		Microsoft::WRL::Callback<
			ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler
		>(
			this, &webview_t::on_env_created
		).Get()
	);
	if (FAILED(hr))
		defer_call(hwnd, [this, hr] { if (on_create) on_create(hr); });
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
	if (closed)
		return;
	closed = true;

	if (ctrl)
		ctrl->Close();

	core.Reset();
	ctrl.Reset();
	env.Reset();

	defer_call(hwnd, [this] { DestroyWindow(hwnd); });
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
		Microsoft::WRL::Callback<
			ICoreWebView2ExecuteScriptCompletedHandler
		>(
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
		defer_call(hwnd, [this, hr] { if (on_create) on_create(hr); });
		return S_OK;
	}
	env = e;

	hr = env->CreateCoreWebView2Controller(
		hwnd,
		Microsoft::WRL::Callback<
			ICoreWebView2CreateCoreWebView2ControllerCompletedHandler
		>(
			this, &webview_t::on_ctrl_created
		).Get()
	);
	if (FAILED(hr))
		defer_call(hwnd, [this, hr] { if (on_create) on_create(hr); });
	return S_OK;
}

HRESULT webview_t::on_ctrl_created(HRESULT hr, ICoreWebView2Controller *c)
{
	if (FAILED(hr)) {
		defer_call(hwnd, [this, hr] { if (on_create) on_create(hr); });
		return S_OK;
	}

	ctrl = c;

	hr = ctrl->get_CoreWebView2(&core);
	if (FAILED(hr)) {
		defer_call(hwnd, [this, hr] { if (on_create) on_create(hr); });
		return S_OK;
	}

	if (!assets_dir.empty()) {
		Microsoft::WRL::ComPtr<ICoreWebView2_3> core3;
		if (SUCCEEDED(core.As(&core3)))
			core3->SetVirtualHostNameToFolderMapping(
				L"assets", assets_dir.c_str(),
				COREWEBVIEW2_HOST_RESOURCE_ACCESS_KIND_ALLOW);
	}

	EventRegistrationToken token;
	core->add_WebMessageReceived(
		Microsoft::WRL::Callback<
			ICoreWebView2WebMessageReceivedEventHandler
		>(
			this, &webview_t::on_web_msg_received
		).Get(),
		&token
	);

	core->add_NavigationCompleted(
		Microsoft::WRL::Callback<
			ICoreWebView2NavigationCompletedEventHandler
		>(
			[this](
				ICoreWebView2 *,
				ICoreWebView2NavigationCompletedEventArgs *args
			) -> HRESULT {
				if (!on_load)
					return S_OK;
				BOOL success = FALSE;
				COREWEBVIEW2_WEB_ERROR_STATUS status =
					COREWEBVIEW2_WEB_ERROR_STATUS_UNKNOWN;
				int http = 0;
				if (args) {
					args->get_IsSuccess(&success);
					args->get_WebErrorStatus(&status);
					Microsoft::WRL::ComPtr<
						ICoreWebView2NavigationCompletedEventArgs2
					> args2;
					if (SUCCEEDED(args->QueryInterface(
						IID_PPV_ARGS(&args2))))
						args2->get_HttpStatusCode(&http);
				}
				on_load(success == TRUE, status, http);
				return S_OK;
			}
		).Get(),
		&token
	);

	core->add_DocumentTitleChanged(
		Microsoft::WRL::Callback<
			ICoreWebView2DocumentTitleChangedEventHandler
		>(
			[this](ICoreWebView2 *sender, IUnknown *) -> HRESULT {
				if (!on_title)
					return S_OK;
				LPWSTR title = nullptr;
				sender->get_DocumentTitle(&title);
				std::wstring t = title ? title : L"";
				CoTaskMemFree(title);
				on_title(t);
				return S_OK;
			}
		).Get(),
		&token
	);

	core->add_ProcessFailed(
		Microsoft::WRL::Callback<
			ICoreWebView2ProcessFailedEventHandler
		>(
			[this](
				ICoreWebView2 *,
				ICoreWebView2ProcessFailedEventArgs *args
			) -> HRESULT {
				if (!on_process_failed || !args)
					return S_OK;
				COREWEBVIEW2_PROCESS_FAILED_KIND kind =
					COREWEBVIEW2_PROCESS_FAILED_KIND_BROWSER_PROCESS_EXITED;
				args->get_ProcessFailedKind(&kind);
				COREWEBVIEW2_PROCESS_FAILED_REASON reason =
					COREWEBVIEW2_PROCESS_FAILED_REASON_UNEXPECTED;
				int exit_code = 0;
				Microsoft::WRL::ComPtr<
					ICoreWebView2ProcessFailedEventArgs2
				> args2;
				if (SUCCEEDED(args->QueryInterface(
					IID_PPV_ARGS(&args2)))) {
					args2->get_Reason(&reason);
					args2->get_ExitCode(&exit_code);
				}
				on_process_failed(kind, reason, exit_code);
				return S_OK;
			}
		).Get(),
		&token
	);

	core->add_WindowCloseRequested(
		Microsoft::WRL::Callback<
			ICoreWebView2WindowCloseRequestedEventHandler
		>(
			[this](ICoreWebView2 *, IUnknown *) -> HRESULT {
				if (on_close_requested)
					on_close_requested();
				return S_OK;
			}
		).Get(),
		&token
	);

	core->AddScriptToExecuteOnDocumentCreated(api,
		Microsoft::WRL::Callback<
			ICoreWebView2AddScriptToExecuteOnDocumentCreatedCompletedHandler
		>(
			[](HRESULT, LPCWSTR) -> HRESULT { return S_OK; }
		).Get()
	);

	RECT bounds = {};
	GetClientRect(hwnd, &bounds);
	ctrl->put_Bounds(bounds);

	defer_call(hwnd, [this, hr] { if (on_create) on_create(hr); });
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

		if (on_msg)
			on_msg(json);
	} catch (...) {}

	return S_OK;
}
