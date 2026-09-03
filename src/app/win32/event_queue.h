#ifndef EVENT_QUEUE_H
#define EVENT_QUEUE_H

#include <deque>
#include <functional>
#include <mutex>
#include <optional>
#include <string>

class event_queue_t {
public:
	/* event handler */
	using callback_t = std::function<void(std::string)>;

	event_queue_t(void) = default;
	~event_queue_t(void) = default;

	event_queue_t(const event_queue_t&) = delete;
	event_queue_t &operator=(const event_queue_t&) = delete;

	/* Enqueue one event from any thread.
	 *
	 * event is JSON encoded object representing the event (UTF-8).
	 */
	bool push(std::string event);

	/* Register a callback for the next event.
	 *
	 * Fires callback on next event (fires immediately if one is waiting).
	 * Only one callback is held at a time. Returns false without firing
	 * callback if event queue is shut down.
	 */
	bool set_cb(callback_t callback);

	/* Drop the pending callback and any queued events. Further push() and
	 * set_cb() calls return false.
	 */
	void abort(void);

private:
	mutable std::mutex mut;
	std::optional<std::deque<std::string>> q = std::deque<std::string>();
	callback_t cb;
};

#endif /* EVENT_QUEUE_H */
