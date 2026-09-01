#include "js_queue.h"
#include <cassert>
#include <nlohmann/json.hpp>
#include <wrl.h>
#include "utf8.h"

void JsQueue::push(const std::wstring& script, Callback&& cb)
{
	/* Wrap a frontend call so its result comes back in a shape this host
	 * can decode. ExecuteScript does not await promises, so the wrapper is
	 * synchronous: it returns the value on success or the caught error on a
	 * throw, always as a plain object so the JSON round-trips. undefined is
	 * mapped to null so JSON.stringify keeps the value key and the envelope
	 * stays recognizable.
	 */
	auto js =
		L"(function () {\n"
		L"  try {\n"
		L"    var value = (" + script + L");\n"
		L"    return { ok: true, "
			L"value: value === undefined ? null : value };\n"
		L"  } catch (error) {\n"
		L"    return {\n"
		L"      ok: false,\n"
		L"      error: {\n"
		L"        name: (error && error.name) || 'Error',\n"
		L"        message: (error && error.message) || String(error),\n"
		L"        stack: error && error.stack\n"
		L"      }\n"
		L"    };\n"
		L"  }\n"
		L"})()";

	std::lock_guard lock(m_);
	q_.emplace_back(std::move(js), std::move(cb));
}

bool JsQueue::empty(void) const
{
	std::lock_guard lock(m_);
	return q_.empty();
}

bool JsQueue::busy(void) const
{
	std::lock_guard lock(m_);
	return running_ != std::nullopt;
}

void JsQueue::abort(void)
{
	std::deque<Entry> q;
	{
		std::lock_guard lock(m_);
		q.swap(q_);
	}
	for (const auto& e : q) {
		try {
			e.cb(E_ABORT, {});
		} catch (...) {
			/* exception during callback */
		}
	}
}

void JsQueue::process(Microsoft::WRL::ComPtr<ICoreWebView2> core)
{
	using script_cpl_t = ICoreWebView2ExecuteScriptCompletedHandler;

	for (;;) {
		std::wstring script;
		{
			std::lock_guard lock(m_);
			if (running_ != std::nullopt)
				return;
			if (q_.empty())
				return;

			running_ = std::move(q_.front());
			q_.pop_front();
			script = running_->script;
		}

		HRESULT hr = E_ABORT; /* webview gone */
		if (core) {
			hr = core->ExecuteScript(
				script.c_str(),
				Microsoft::WRL::Callback<script_cpl_t>(
					[this, core](HRESULT hr, LPCWSTR json)
					-> HRESULT {
						this->on_done(hr, json);
						process(core);
						return S_OK;
					}
				).Get()
			);
		}

		if (SUCCEEDED(hr))
			return;

		/* failed to start script */
		Callback cb;
		{
			std::lock_guard lock(m_);
			cb = std::move(running_->cb);
			running_.reset();
		}
		try {
			cb(hr, {});
		} catch (...) {
			/* exception during callback */
		}
	}
}

void JsQueue::on_done(HRESULT hr, LPCWSTR json_str) noexcept
{
	std::wstring obj;
	try {
		nlohmann::json doc;

		if (SUCCEEDED(hr) && json_str) {
			doc = nlohmann::json::parse(
				wstr_to_utf8(json_str), nullptr, false
			);
		}
		if (SUCCEEDED(hr)) {
			if (!doc.is_object() ||
			    !doc.contains("ok") ||
			    !doc["ok"].is_boolean()
			)
				hr = E_UNEXPECTED;
		}
		if (SUCCEEDED(hr)) {
			hr = E_UNEXPECTED;
			bool ok = doc["ok"].get<bool>();

			if (ok && doc.contains("value")) {
				hr = S_OK;
				obj = utf8_to_wstr(doc["value"].dump());
			} else if (!ok && doc.contains("error")) {
				hr = E_FAIL;
				obj = utf8_to_wstr(doc["error"].dump());
			}
		}
	} catch (...) {
		hr = E_UNEXPECTED;
	}

	Callback cb;
	{
		std::lock_guard lock(m_);
		assert(running_ != std::nullopt);
		cb = std::move(running_->cb);
		running_.reset();
	}
	try {
		cb(hr, obj);
	} catch (...) {
		/* exception during callback */
	}
}
