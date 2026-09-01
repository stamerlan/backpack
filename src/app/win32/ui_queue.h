#ifndef UI_QUEUE_H
#define UI_QUEUE_H

#include <deque>
#include <functional>
#include <mutex>
#include <optional>
#include <string>
#include <utility>

#include <windows.h>

class ui_queue_t {
public:
	/* Result of a scheduled script.
	 *
	 * hresult is S_OK when the script ran, then string contains a json
	 * object, or a pywebviewJavascriptError420 object on a JS throw (same
	 * as pywebview).
	 * 
	 * A failure HRESULT marks a transport error (webview gone or the call
	 * never started) and the string parameter is empty.
	 */
	using callback_t = std::function<void(HRESULT, const std::wstring&)>;

	ui_queue_t(void) = default;
	~ui_queue_t(void) = default;

	ui_queue_t(const ui_queue_t&) = delete;
	ui_queue_t &operator=(const ui_queue_t&) = delete;

	/* Enqueue a script and the callback that settles its result.
	 *
	 * Thread safe. The entry waits until next() hands it out to run.
	 */
	void push(const std::wstring& script, callback_t&& cb);

	/* Take the next script and mark it running.
	 *
	 * Thread safe. Returns nullopt when a script already runs or the queue
	 * is empty, so at most one runs at a time. The entry stays owned by the
	 * queue until complete() settles it. The caller runs the script on
	 * whatever thread the webview needs and reports back.
	 */
	std::optional<std::wstring> next(void);

	/* Settle the running script and clear the running slot.
	 *
	 * Thread safe. Fires the entry's callback with hresult and json. No-op
	 * when nothing is running.
	 */
	void complete(HRESULT hresult, const std::wstring& json);

	bool busy(void) const;
	bool empty(void) const;

	/* Fail every pending call with E_ABORT */
	void abort(void);

private:
	struct entry_t {
		std::wstring script;
		callback_t cb;
	};

	mutable std::mutex mut;
	std::deque<entry_t> q;
	std::optional<entry_t> cur_ent; /* current running entry */
};

#endif /* UI_QUEUE_H */
