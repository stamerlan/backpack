#ifndef MSG_IDS_H
#define MSG_IDS_H

#include <windows.h>

/* Posted to the host window once the WebView2 environment and controller have
 * finished construction (successfully or failed).
 *   - wParam (webview_t *): instance pointer.
 *   - lParam (HRESULT): construction status. S_OK on success.
 */
constexpr UINT WM_WEBVIEW_RDY = WM_APP + 0;

/* Posted to the host window once webview teardown has finished.
 *   - wParam (webview_t *): instance pointer.
 */
constexpr UINT WM_WEBVIEW_CLOSE = WM_APP + 1;

/* Posted to the host window by call_q::call_later() to run queued closures on
 * the UI thread.
 */
constexpr UINT WM_CALL = WM_APP + 2;

/* Posted to the host window by app_t::quit() from the core thread to tear the
 * app down. Window destruction must run on the UI thread that owns the
 * window, so quit() only posts and the pump does the teardown.
 */
constexpr UINT WM_APP_QUIT = WM_APP + 3;

#endif /* MSG_IDS_H */
