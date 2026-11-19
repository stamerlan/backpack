#ifndef SCRIPT_QUEUE_H
#define SCRIPT_QUEUE_H

#include <functional>
#include <map>
#include <mutex>
#include <string>

#include <windows.h>

#include "webview.h"

typedef struct _object PyObject;

class script_queue_t {
public:
	/* Result of a script.
	 *
	 * hresult:
	 *   - S_OK: the script's value settled, then string contains it as
	 *     JSON. If JS code throws or rejects, a pywebviewJavascriptError420
	 *     JSON object is returned (same as pywebview).
	 *   - E_ABORT: queue was aborted or the webview is gone. String
	 *     argument is empty.
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

	/* Enqueue a script for execution. Scripts start in submission order.
	 *
	 * Thread safe. cb fires exactly once on the UI thread (or on the
	 * calling thread when the UI thread is gone). Returns false without
	 * queuing or firing cb after abort().
	 */
	bool exec_script(const std::wstring& script, callback_t cb);

	/* Settle a script with the result message its wrapper posted.
	 *
	 * Returns false when msg is not a script result, true otherwise (also
	 * when the script is already settled or aborted and the result is
	 * dropped).
	 */
	bool process_cpl_msg(const std::wstring& msg);

	/* Settle script by ID. The script callback is executed in current
	 * thread.
	 *
	 * If the script ID is already settled or aborted - does nothing.
	 */
	void settle_script(uint64_t id, HRESULT hr,
		const std::wstring& json) noexcept;

	/* Abort pending scripts with E_ABORT and reject further exec_script()
	 * calls. A script not started yet never runs (a script about to start
	 * might still start after abort returns). Already started may execute,
	 * their results are dropped (exactly one callback call per
	 * exec_script() guarantee).
	 *
	 * Thread safe. Callbacks fire on the calling thread. A late result of
	 * the aborted running script is dropped.
	 */
	void abort(void);

	/* New reference to a new Python object (native.win32.ScriptQueue)
	 * borrowing this queue, or nullptr with a Python error set. Requires
	 * the GIL.
	 */
	PyObject *to_py(void);

private:
	HWND hwnd;
	webview_t& view;

	mutable std::mutex mut;
	std::map<uint64_t, callback_t> cb_map;
	uint64_t next_id = 0;
	bool aborted = false; /* if set exec_script() calls are rejected */
};

#endif /* SCRIPT_QUEUE_H */
