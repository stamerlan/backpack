#include "event_queue.h"

#include <utility>

bool EventQueue::post(Event event)
{
	std::function<void(Event)> cb;
	{
		std::lock_guard lock(m_);
		if (!running_)
			return false;
		if (!cb_) {
			q_.push_back(std::move(event));
			return true;
		}
		cb = std::move(cb_);
		cb_ = nullptr;
	}

	/* Deliver outside the lock so a callback that re-enters get() from
	 * itself cannot deadlock.
	 */
	cb(std::move(event));
	return true;
}

bool EventQueue::get(std::function<void(Event)> cb)
{
	Event event;
	{
		std::lock_guard lock(m_);
		if (!running_)
			return false;
		if (q_.empty()) {
			cb_ = std::move(cb);
			return true;
		}
		event = std::move(q_.front());
		q_.pop_front();
	}

	cb(std::move(event));
	return true;
}

void EventQueue::shutdown(void)
{
	std::lock_guard lock(m_);
	running_ = false;
	cb_ = nullptr;
	q_.clear();
}
