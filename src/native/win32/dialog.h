#ifndef DIALOG_H
#define DIALOG_H

#include <expected>
#include <functional>
#include <vector>
#include <string>
#include <utility>

#include <windows.h>

namespace dialog {

using filters_t = std::vector<std::pair<std::wstring, std::wstring>>;

/* Selected paths, or the failure. The error is
 * HRESULT_FROM_WIN32(ERROR_CANCELLED) when the user dismissed the dialog.
 */
using result_t = std::expected<std::vector<std::wstring>, HRESULT>;

/* Show the dialog modally over the owner window */
using show_t = std::function<result_t(HWND owner)>;

show_t open(bool select_multiple, filters_t filters);
show_t save(std::wstring filename, filters_t filters);

} /* namespace dialog */

#endif /* DIALOG_H */
