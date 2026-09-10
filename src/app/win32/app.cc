#include "app.h"

#include <format>
#include <mutex>
#include <optional>
#include <utility>
#include <vector>

#include "call_q.h"
#include "msg_ids.h"
#include "utf8.h"

LRESULT CALLBACK app_t::wnd_proc(HWND hwnd, UINT m, WPARAM wp, LPARAM lp)
{
	auto *self = reinterpret_cast<app_t *>(
		GetWindowLongPtrW(hwnd, GWLP_USERDATA));
	if (!self)
		return DefWindowProcW(hwnd, m, wp, lp);

	switch (m) {
	case WM_SIZE: {
		RECT r = { 0, 0, LOWORD(lp), HIWORD(lp) };
		self->webview_.resize(r);
		return 0;
	}
	case WM_WEBVIEW_RDY: {
		HRESULT hr = static_cast<HRESULT>(lp);
		if (FAILED(hr)) {
			MessageBoxW(hwnd, std::format(
				L"WebView2 failed to start (0x{:08X})",
				static_cast<unsigned>(hr)).c_str(),
				L"Backpack", MB_OK | MB_ICONERROR);
			DestroyWindow(hwnd);
			return 0;
		}
		self->webview_.navigate(self->url);
		return 0;
	}
	case WM_CLOSE:
		/* Hand the close attempt to Core as an event and keep the
		 * window open: Core runs its shutdown (save prompt) and calls
		 * quit() when it is done. If the event bridge is already down
		 * (Core gone), close directly so the window is not stuck open.
		 */
		if (!self->event_q.push("{ \"name\": \"close\", \"args\": [] }"))
			self->webview_.close();
		return 0;
	case WM_WEBVIEW_CLOSE:
		DestroyWindow(hwnd);
		return 0;
	case WM_APP_QUIT:
		self->webview_.close();
		return 0;
	case WM_CALL:
		call_dispatch(wp);
		return 0;
	case WM_SETTINGCHANGE:
		/* The OS posts this (lParam "ImmersiveColorSet") when the apps
		 * theme changes. Re-apply the chosen mode so a "system" title
		 * bar follows the OS and an explicit choice is not reset.
		 */
		if (lp && CompareStringOrdinal(
			reinterpret_cast<PCWSTR>(lp), -1,
			L"ImmersiveColorSet", -1, TRUE) == CSTR_EQUAL) {
			std::wstring mode;
			{
				std::lock_guard lock(self->theme_m_);
				mode = self->theme;
			}
			if (!mode.empty())
				self->window_.set_theme(mode);
		}
		return 0;
	case WM_DESTROY:
		PostQuitMessage(0);
		return 0;
	default:
		return DefWindowProcW(hwnd, m, wp, lp);
	}
}

app_t::app_t(HWND hwnd, ATOM atom, std::wstring url, std::wstring assets)
	: window_(hwnd, atom),
	webview_(
		[this](std::string json) -> HRESULT {
			event_q.push(std::move(json));
			return S_OK;
		},
		[this] (void) {
			event_q.push("{ \"name\": \"load\", \"args\": [] }");
		}
	),
	url(std::move(url))
{
	SetWindowLongPtrW(hwnd, GWLP_USERDATA,
		reinterpret_cast<LONG_PTR>(this));
	webview_.create(hwnd, L"", assets);
}

void app_t::quit(void) const noexcept
{
	if (HWND hwnd = window_.hwnd())
		PostMessageW(hwnd, WM_APP_QUIT, 0, 0);
}

bool app_t::get_event(std::function<void(std::string)> cb)
{
	return event_q.set_cb(std::move(cb));
}

void app_t::set_title(std::wstring title)
{
	call_later(window_.hwnd(), [this, title = std::move(title)] {
		window_.set_title(title);
	});
}

void app_t::hide(void)
{
	call_later(window_.hwnd(), [this] { window_.hide(); });
}

void app_t::set_theme(std::wstring mode)
{
	{
		std::lock_guard lock(theme_m_);
		theme = mode;
	}
	call_later(window_.hwnd(), [this, mode = std::move(mode)] {
		window_.set_theme(mode);
	});
}

void app_t::show_open_dialog(
	bool multiple,
	std::vector<std::pair<std::wstring, std::wstring>> filters,
	std::function<void(dialog_t::result_t)> cb)
{
	dialog_t d;
	try {
		d = dialog_t::open_dialog(multiple, filters);
	} catch (...) {
		if (cb)
			cb({ .hresult = E_FAIL });
		return;
	}
	show_dialog(std::move(d), std::move(cb));
}

void app_t::show_save_dialog(std::wstring filename,
	std::vector<std::pair<std::wstring, std::wstring>> filters,
	std::function<void(dialog_t::result_t)> cb)
{
	dialog_t d;
	try {
		d = dialog_t::save_dialog(std::move(filename), filters);
	} catch (...) {
		if (cb)
			cb({ .hresult = E_FAIL });
		return;
	}
	show_dialog(std::move(d), std::move(cb));
}

void app_t::show_dialog(dialog_t d, std::function<void(dialog_t::result_t)> cb)
{
	{
		std::lock_guard lock(dialog_m_);
		if (dialog_) {
			/* a dialog is already open */
			if (cb) {
				dialog_t::result_t r = {
					.hresult =
						HRESULT_FROM_WIN32(ERROR_BUSY)
				};
				cb(r);
			}
			return;
		}
		dialog_ = std::move(d);
	}

	/* show() runs a modal loop, so it must run on the UI thread */
	call_later(window_.hwnd(), [this, cb = std::move(cb)] {
		dialog_t::result_t r = dialog_->show(window_.hwnd());
		{
			std::lock_guard lock(dialog_m_);
			dialog_.reset();
		}
		if (cb)
			cb(std::move(r));
	});
}

void app_t::eval_js(std::wstring js, ui_queue_t::callback_t cb)
{
	ui_q.push(js, std::move(cb));
	call_later(window_.hwnd(), [this] { ui_q_run(); });
}

void app_t::ui_q_run(void)
{
	for (;;) {
		auto script = ui_q.next();
		if (!script)
			return;

		HRESULT hr = webview_.execute_script(
			*script,
			[this](HRESULT hr, const std::wstring& json) {
				ui_q.complete(hr, json);
				ui_q_run();
			}
		);

		if (SUCCEEDED(hr))
			return;

		/* failed to start script */
		ui_q.complete(hr, {});
	}
}
