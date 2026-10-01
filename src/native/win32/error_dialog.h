#ifndef ERROR_DIALOG_H
#define ERROR_DIALOG_H

#include <stacktrace>
#include <string>
#include <windows.h>

/* Log a fatal error at CRITICAL and show it to the user in a task dialog:
 * the first line of text is the headline, the rest goes under "Details" and
 * the log path is a link to the log. A trace goes to the log only.
 */
void show_fatal(const std::wstring& text, HWND owner = nullptr,
	const std::stacktrace *trace = nullptr);

#endif /* ERROR_DIALOG_H */
