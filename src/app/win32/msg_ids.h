#ifndef MSG_IDS_H
#define MSG_IDS_H

#include <windows.h>

/* Posted to the host window once the WebView2 environment and controller have
 * finished construction (successfully or failed).
 *   - wParam (Webview *): instance pointer.
 *   - lParam (HRESULT): construction status. S_OK on success.
 */
constexpr UINT WM_WEBVIEW_RDY = WM_APP + 0;

/* Posted to the host window once webview teardown has finished.
 *   - wParam (Webview *): instance pointer.
 */
constexpr UINT WM_WEBVIEW_CLOSE = WM_APP + 1;

/* Posted to the host window by call_q::call_later() to run queued closures on
 * the UI thread.
 */
constexpr UINT WM_CALL = WM_APP + 2;

#endif /* MSG_IDS_H */
