#ifndef CALL_Q_H
#define CALL_Q_H

#include <functional>
#include <windows.h>

/* Post fn to run on the UI thread that owns hwnd. The closure is heap allocated
 * and carried as the WM_CALL wParam. The window procedure runs and frees it
 * with call_dispatch().
 *
 * If the post fails (window gone, thread message queue full) the closure is
 * freed here and never runs.
 *
 * Thread safe.
 */
void call_later(HWND hwnd, std::function<void()> fn);

/* Run and free the closure carried by a WM_CALL message.
 * Call from the WM_CALL handler.
 */
void call_dispatch(WPARAM wp) noexcept;

/* Free any WM_CALL still enqueued closures */
void call_cancel(void);

#endif /* CALL_Q_H */
