#ifndef SCRIPT_QUEUE_H
#define SCRIPT_QUEUE_H

#include <deque>
#include <functional>
#include <mutex>
#include <optional>
#include <string>

#include <windows.h>

#include "webview.h"

class script_queue_t {
public:
	/* Result of a script.
	 *
	 * hresult:
	 *   - E_OK: the script ran, then string contains a json object.
	 *     If JS code throw a pywebviewJavascriptError420 JSON object is
	 *     returned (same as pywebview).
	 *   - E_ABORT: queue was aborted or the webview is gone. The call never
	 *     started. String argument is empty. 
	 *   - Any other failure the call never started or failed in flight.
	 */
	using callback_t = std::function<void(HRESULT, const std::wstring&)>;

	/* Scripts run through webview on the UI thread that owns hwnd.
	 * Both must outlive the queue.
	 */
	script_queue_t(HWND hwnd, webview_t& view);
	~script_queue_t(void) = default;

	script_queue_t(const script_queue_t&) = delete;
	script_queue_t &operator=(const script_queue_t&) = delete;

	/* Enqueue a script and run it once the scripts ahead of it settle.
	 *
	 * Thread safe. cb fires exactly once on the UI thread (or on the
	 * calling thread when the UI thread is gone). Returns false without
	 * queuing or firing cb after abort().
	 */
	bool exec_script(const std::wstring& script, callback_t cb);

	/* Fail the running and every queued script with E_ABORT and reject
	 * further exec_script() calls.
	 *
	 * Thread safe. Callbacks fire on the calling thread. A late result of
	 * the aborted running script is dropped.
	 */
	void abort(void);

private:
	struct entry_t {
		std::wstring script;
		callback_t cb;
	};

	/* UI thread: start queued scripts until one is in flight. */
	void pump(void);

	/* Settle the running script and clear the running slot. */
	void settle(HRESULT hr, const std::wstring& json);

	HWND hwnd;
	webview_t& view;

	mutable std::mutex mut;
	/* nullopt once aborted */
	std::optional<std::deque<entry_t>> q = std::deque<entry_t>();
	std::optional<entry_t> cur_ent; /* current running entry */
};

#endif /* SCRIPT_QUEUE_H */
