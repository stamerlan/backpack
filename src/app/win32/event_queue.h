#ifndef EVENT_QUEUE_H
#define EVENT_QUEUE_H

#include <deque>
#include <functional>
#include <mutex>
#include <string>

class EventQueue {
public:
	/* One inbound event: a frontend call or an OS lifecycle notice.
	 *
	 * name is the event/handler name. args is the JSON array of arguments,
	 * both UTF-8. OS events such as load and close carry an empty args
	 * array.
	 */
	struct Event {
		std::string name;
		std::string args;
	};

	EventQueue(void) = default;
	~EventQueue(void) = default;

	EventQueue(const EventQueue&) = delete;
	EventQueue &operator=(const EventQueue&) = delete;

	/* Enqueue one event from any thread.
	 *
	 * A pending callback is handed the event directly; otherwise the event
	 * is queued until get() is called. Returns false if shut down.
	 */
	bool post(Event event);

	/* Register a callback for the next event.
	 *
	 * Fires cb right away with a queued event if one is waiting. Otherwise
	 * stores cb until the next post(). Only one callback is held at a time.
	 * Returns false without firing cb once shut down.
	 */
	bool get(std::function<void(Event)> cb);

	/* Drop the pending callback and any queued events; further post() and
	 * get() calls return false.
	 */
	void shutdown(void);

private:
	mutable std::mutex m_;
	std::deque<Event> q_;
	std::function<void(Event)> cb_;
	bool running_ = true;
};

#endif /* EVENT_QUEUE_H */
