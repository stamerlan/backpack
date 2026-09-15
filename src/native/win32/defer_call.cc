#include "defer_call.h"
#include <memory>
#include <utility>
#include "winerr.h"

void defer_call(HWND hwnd, std::function<void()> fn)
{
	auto p = std::make_unique<std::function<void()>>(std::move(fn));
	if (!PostMessageW(hwnd, WM_APP, reinterpret_cast<WPARAM>(p.get()), 0))
		throw win32_error("PostMessageW()");
	p.release();	/* the message owns the closure now */
}

void defer_call_run(WPARAM wp) noexcept
try {
	std::unique_ptr<std::function<void()>> fn(
		reinterpret_cast<std::function<void()> *>(wp)
	);

	if (fn && *fn)
		(*fn)();
} catch (...) {
	/* no exception may propagate out of WndProc */
}

void defer_call_cancel(HWND hwnd)
{
	MSG m;
	while (PeekMessageW(&m, hwnd, WM_APP, WM_APP, PM_REMOVE)) {
		std::unique_ptr<std::function<void()>> fn(
			reinterpret_cast<std::function<void()> *>(m.wParam)
		);
	}
}
