#ifndef JS_QUEUE_H
#define JS_QUEUE_H

#include <deque>
#include <functional>
#include <mutex>
#include <optional>
#include <string>
#include <utility>

#include <wrl/client.h>
#include <WebView2.h>

class JsQueue {
public:
	/* Result of a scheduled script.
	 *
	 * status: S_OK when the call returned a value, then json is that value
	 *   as JSON. A failure HRESULT otherwise: json holds the thrown error
	 *   as an object on a JS exception, or is empty on a transport failure.
	 */
	using Callback = std::function<
		void(HRESULT hresult, const std::wstring& json)
	>;

	JsQueue(void) = default;
	~JsQueue(void) = default;

	JsQueue(const JsQueue&) = delete;
	JsQueue &operator=(const JsQueue&) = delete;

	/* Schedule a script execution.
	 *
	 * Thread safe. Scripts are executed one at a time. Callback fires in
	 * submission order and the next call starts only once the prior one
	 * settles.
	 * 
	 * Call process() to execute the next script in queue.
	 */
	void push(const std::wstring& script, Callback&& cb);

	/* Whether the queue holds no entries. */
	bool empty(void) const;

	/* If any script is running */
	bool busy(void) const;

	/* Abort all pending javascript calls */
	void abort(void);

	/* Run next js script (if none is running). */
	void process(Microsoft::WRL::ComPtr<ICoreWebView2> core);

private:
	struct Entry {
		std::wstring script;
		Callback cb;
	};

	void on_done(HRESULT hr, LPCWSTR json_str) noexcept;

	mutable std::mutex m_;
	std::deque<Entry> q_;
	std::optional<Entry> running_;
};

#endif /* JS_QUEUE_H */
