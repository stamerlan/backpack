#include "script_queue.h"
#include <utility>
#include "defer_call.h"

/* turn a JS throw into a pywebviewJavascriptError420 object, the same shape
 * as pywebview uses
 */
static std::wstring wrap_script(const std::wstring& script)
{
	return
		L"(function () {\n"
		L"  var to_error = function (e) {\n"
		L"    var err = {\n"
		L"      name: e && e.name,\n"
		L"      pywebviewJavascriptError420: true\n"
		L"    };\n"
		L"    if (e) Object.getOwnPropertyNames(e).forEach(function (k) {\n"
		L"      err[k] = e[k];\n"
		L"    });\n"
		L"    return err;\n"
		L"  };\n"
		L"  try {\n"
		L"    var value = (" + script + L");\n"
		L"    return value === undefined ? null : value;\n"
		L"  } catch (e) {\n"
		L"    return to_error(e);\n"
		L"  }\n"
		L"})()";
}

script_queue_t::script_queue_t(HWND hwnd, webview_t& view)
	: hwnd(hwnd), view(view)
{
}

bool script_queue_t::exec_script(const std::wstring& script, callback_t cb)
{
	auto js = wrap_script(script);
	bool idle;
	{
		std::lock_guard lock(mut);
		if (!q)
			return false;
		q->emplace_back(std::move(js), std::move(cb));
		idle = cur_ent == std::nullopt;
	}

	/* a script in flight pumps the next one when it settles */
	if (!idle)
		return true;
	try {
		defer_call(hwnd, [this] { pump(); });
	} catch (...) {
		/* the post failed (window gone), nothing will run the queue */
		abort();
	}
	return true;
}

void script_queue_t::abort(void)
{
	std::deque<entry_t> abort_q;
	std::optional<entry_t> ent;
	{
		std::lock_guard lock(mut);
		if (!q)
			return;
		abort_q.swap(*q);
		q.reset();
		ent = std::move(cur_ent);
		cur_ent.reset();
	}
	if (ent)
		abort_q.push_front(std::move(*ent));
	for (const auto& e : abort_q) {
		try {
			e.cb(E_ABORT, {});
		} catch (...) {
			/* exception during callback */
		}
	}
}

void script_queue_t::pump(void)
{
	for (;;) {
		std::wstring script;
		{
			std::lock_guard lock(mut);
			if (!q || q->empty() || cur_ent != std::nullopt)
				return;
			cur_ent = std::move(q->front());
			q->pop_front();
			script = cur_ent->script;
		}

		HRESULT hr = view.execute_script(script,
			[this](HRESULT hr, const std::wstring& json) {
				settle(hr, json);
				pump();
			});
		if (SUCCEEDED(hr))
			return;
		/* the call never started, settle it and go on to the next */
		settle(hr, {});
	}
}

void script_queue_t::settle(HRESULT hr, const std::wstring& json)
{
	std::optional<entry_t> ent;
	{
		std::lock_guard lock(mut);
		if (cur_ent == std::nullopt)
			return;
		ent = std::move(cur_ent);
		cur_ent.reset();
	}
	try {
		ent->cb(hr, json);
	} catch (...) {
		/* exception during callback */
	}
}
