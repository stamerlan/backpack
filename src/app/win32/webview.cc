#include "webview.h"
#include <wrl.h>
#include "msg_ids.h"

using Microsoft::WRL::Callback;

using env_cpl_cb = ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler;
using ctrl_cpl_cb = ICoreWebView2CreateCoreWebView2ControllerCompletedHandler;

void WebView::create(HWND parent_hwnd, const std::wstring& user_data_dir)
{
	hwnd_ = parent_hwnd;

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

	RECT bounds = {};
	GetClientRect(hwnd_, &bounds);
	ctrl_->put_Bounds(bounds);

	PostMessageW(hwnd_, WM_WEBVIEW_RDY,
		reinterpret_cast<WPARAM>(this), static_cast<LPARAM>(hr)
	);
	return S_OK;
}
