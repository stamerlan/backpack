#include "event_queue.h"

#include <utility>

bool event_queue_t::push(std::string event)
{
	std::function<void(std::string)> callback;
	{
		std::lock_guard lock(mut);
		if (!q)
			return false;
		if (!cb) {
			q->push_back(std::move(event));
			return true;
		}
		callback = std::move(cb);
		cb = nullptr;
	}

	callback(std::move(event));
	return true;
}

bool event_queue_t::set_cb(std::function<void(std::string)> callback)
{
	std::string event;
	{
		std::lock_guard lock(mut);
		if (!q)
			return false;
		if (q->empty()) {
			cb = std::move(callback);
			return true;
		}
		event = std::move(q->front());
		q->pop_front();
	}

	callback(std::move(event));
	return true;
}

void event_queue_t::abort(void)
{
	std::lock_guard lock(mut);
	q.reset();
	cb = nullptr;
}
