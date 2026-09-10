#ifndef MSG_IDS_H
#define MSG_IDS_H

#include <windows.h>

/* Posted to the host window by call_q::call_later() to run queued closures on
 * the UI thread.
 */
constexpr UINT WM_CALL = WM_APP + 0;

/* Posted to the host window by app_t::quit() from the core thread to tear the
 * app down. Window destruction must run on the UI thread that owns the
 * window, so quit() only posts and the pump does the teardown.
 */
constexpr UINT WM_APP_QUIT = WM_APP + 1;

#endif /* MSG_IDS_H */
