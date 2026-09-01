#include "ui_queue.h"

void ui_queue_t::push(const std::wstring& script, callback_t&& cb)
{
	/* turn a JS throw into a pywebviewJavascriptError420 object, the same
	 * shape as pywebview uses
	 */
	auto js =
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

	std::lock_guard lock(mut);
	q.emplace_back(std::move(js), std::move(cb));
}

bool ui_queue_t::empty(void) const
{
	std::lock_guard lock(mut);
	return q.empty();
}

bool ui_queue_t::busy(void) const
{
	std::lock_guard lock(mut);
	return cur_ent != std::nullopt;
}

void ui_queue_t::abort(void)
{
	std::deque<entry_t> abort_q;
	{
		std::lock_guard lock(mut);
		abort_q.swap(q);
	}
	for (const auto& ent : abort_q) {
		try {
			ent.cb(E_ABORT, {});
		} catch (...) {
			/* exception during callback */
		}
	}
}

std::optional<std::wstring> ui_queue_t::next(void)
{
	std::lock_guard lock(mut);
	if (cur_ent != std::nullopt)
		return std::nullopt;
	if (q.empty())
		return std::nullopt;

	cur_ent = std::move(q.front());
	q.pop_front();
	return cur_ent->script;
}

void ui_queue_t::complete(HRESULT hr, const std::wstring& json)
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
