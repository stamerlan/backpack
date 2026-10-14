#include "script_queue.h"
#include <cwchar>
#include <utility>
#include "defer_call.h"
#include "logger.h"
#include "winerr.h"

/* a script result message is "script_cb:<id>:<json>" */
static const std::wstring msg_prefix = L"script_cb:";

/* turn a JS throw into a pywebviewJavascriptError420 object, the same shape
 * as pywebview uses
 */
static std::wstring wrap_script(const std::wstring& script, uint64_t id)
{
	return
		L"(function () {\n"
		L"  var to_error = function (e) {\n"
		L"    var err = {\n"
		L"      name: e && e.name,\n"
		L"      pywebviewJavascriptError420: true\n"
		L"    };\n"
		L"    if (e)\n"
		L"      Object.getOwnPropertyNames(e).forEach(function (k) {\n"
		L"        err[k] = e[k];\n"
		L"      });\n"
		L"    return err;\n"
		L"  };\n"
		L"  var post = function (v) {\n"
		L"    var json;\n"
		L"    try {\n"
		L"      json = JSON.stringify(v === undefined ? null : v);\n"
		L"    } catch (e) {\n"
		L"      try {\n"
		L"        json = JSON.stringify(to_error(e));\n"
		L"      } catch (e2) {\n"
		L"        json = '{\"pywebviewJavascriptError420\":true}';\n"
		L"      }\n"
		L"    }\n"
		L"    window.chrome.webview.postMessage(\"" + msg_prefix
			+ std::to_wstring(id) + L":\" + json);\n"
		L"  };\n"
		L"  try {\n"
		L"    Promise.resolve(" + script + L")\n"
		L"      .then(post, function (e) { post(to_error(e)); });\n"
		L"  } catch (e) {\n"
		L"    post(to_error(e));\n"
		L"  }\n"
		L"})()";
}

bool script_queue_t::process_cpl_msg(const std::wstring& msg)
{
	if (!msg.starts_with(msg_prefix))
		return false;
	const wchar_t *num = msg.c_str() + msg_prefix.size();
	wchar_t *end;
	uint64_t id = wcstoull(num, &end, 10);
	if (end == num || *end != L':')
		return false;
	settle_script(id, S_OK, end + 1);
	return true;
}

script_queue_t::script_queue_t(HWND hwnd, webview_t& view)
	: hwnd(hwnd), view(view)
{
}

bool script_queue_t::exec_script(const std::wstring& script, callback_t cb)
{
	uint64_t id;
	{
		std::lock_guard lock(mut);
		if (aborted)
			return false;
		id = next_id++;
		cb_map[id] = std::move(cb);
	}

	try {
		defer_call(hwnd, [this, js = wrap_script(script, id), id] {
			HRESULT hr;

			{
				std::lock_guard lock(mut);
				if (!cb_map.contains(id))
					return;
			}

			try {
				hr = view.execute_script(js,
					[this, id](HRESULT hr) {
						if (SUCCEEDED(hr))
							return;
						settle_script(id, hr, {});
					}
				);
			} catch (...) {
				hr = E_FAIL;
			}

			if (FAILED(hr))
				settle_script(id, hr, {});
		});
	} catch (...) {
		/* the post failed (window gone) */
		abort();
	}
	return true;
}

void script_queue_t::settle_script(uint64_t id, HRESULT hr,
	const std::wstring& json) noexcept
try {
	callback_t cb;

	{
		std::lock_guard lock(mut);

		auto cb_it = cb_map.find(id);
		if (cb_it == cb_map.end())
			return;

		cb = std::move(cb_it->second);
		cb_map.erase(cb_it);
	}

	if (FAILED(hr) && hr != E_ABORT)
		logger::error("script failed: {}", fmt_err(hr));

	cb(hr, json);
} catch (const traced_error& e) {
	logger::error("script callback failed: {}\nstack trace:\n{}",
		e.what(), std::to_string(e.trace()));
} catch (const std::exception& e) {
	logger::error("script callback failed: {}", e.what());
} catch (...) {
	logger::error("script callback failed: unknown exception");
}

void script_queue_t::abort(void)
{
	std::map<uint64_t, callback_t> abort_map;

	{
		std::lock_guard lock(mut);
		if (aborted)
			return;
		aborted = true;
		cb_map.swap(abort_map);
	}

	for (auto const& [id, cb] : abort_map) {
		try {
			cb(E_ABORT, {});
		} catch (const traced_error& e) {
			logger::error(
				"script callback failed: {}\nstack trace:\n{}",
				e.what(), std::to_string(e.trace()));
		} catch (const std::exception& e) {
			logger::error("script callback failed: {}", e.what());
		} catch (...) {
			logger::error(
				"script callback failed: unknown exception");
		}
	}
}
