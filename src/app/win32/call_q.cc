#include "call_q.h"
#include <memory>
#include <utility>
#include "msg_ids.h"
#include "winerr.h"

void call_later(HWND hwnd, std::function<void()> fn)
{
	auto p = std::make_unique<std::function<void()>>(std::move(fn));
	if (!PostMessageW(hwnd, WM_CALL, reinterpret_cast<WPARAM>(p.get()), 0))
		throw win32_error("PostMessageW()");
	p.release();	/* the message owns the closure now */
}

void call_dispatch(WPARAM wp) noexcept
try {
	std::unique_ptr<std::function<void()>> fn(
		reinterpret_cast<std::function<void()> *>(wp)
	);
	
	if (fn && *fn)
		(*fn)();
} catch (...) {
	/* no exception may propagate out of WndProc */
}

void call_cancel(void)
{
	MSG m;
	while (PeekMessageW(&m, nullptr, WM_CALL, WM_CALL, PM_REMOVE)) {
		std::unique_ptr<std::function<void()>> fn(
			reinterpret_cast<std::function<void()> *>(m.wParam)
		);
	}
}
