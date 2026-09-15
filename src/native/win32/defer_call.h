#ifndef DEFER_CALL_H
#define DEFER_CALL_H

#include <functional>
#include <windows.h>

/* Post fn to run on the UI thread that owns hwnd. The closure is heap allocated
 * and carried as the WM_CALL wParam. The window procedure runs and frees it
 * with defer_call_run().
 *
 * If the post fails (window gone, thread message queue full) the closure is
 * freed here and never runs.
 *
 * Thread safe.
 */
void defer_call(HWND hwnd, std::function<void()> fn);

/* Run and free the closure carried by a WM_APP message. */
void defer_call_run(WPARAM wp) noexcept;

/* Free any WM_CALL still enqueued closures */
void defer_call_cancel(HWND hwnd = nullptr);

#endif /* DEFER_CALL_H */
