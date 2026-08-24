#ifndef MSG_IDS_H
#define MSG_IDS_H

#include <windows.h>

/* Posted to the host window once the WebView2 environment and controller have
 * finished construction (successfully or failed).
 *   - wParam (Webview *): instance pointer.
 *   - lParam (HRESULT): construction status. S_OK on success.
 */
constexpr UINT WM_WEBVIEW_RDY = WM_APP + 0;

#endif /* MSG_IDS_H */
