#ifndef MSG_IDS_H
#define MSG_IDS_H

#include <windows.h>

/* Posted to the host window by call_q::call_later() to run queued closures on
 * the UI thread.
 */
constexpr UINT WM_CALL = WM_APP + 0;

#endif /* MSG_IDS_H */
