#include "error_dialog.h"

#include <commctrl.h>
#include <shellapi.h>

#include "logger.h"
#include "utf8.h"

#pragma comment(lib, "comctl32.lib")
#pragma comment(lib, "shell32.lib")

static HRESULT CALLBACK dialog_cb(HWND hwnd, UINT msg, WPARAM, LPARAM lp,
	LONG_PTR)
{
	if (msg == TDN_HYPERLINK_CLICKED)
		ShellExecuteW(hwnd, L"open", reinterpret_cast<LPCWSTR>(lp),
			nullptr, nullptr, SW_SHOWNORMAL);
	return S_OK;
}

/* The details keep the last 25 lines of text, at most about 2000 characters, so
 * the dialog fits on screen.
 */
void show_fatal(const std::wstring& text, HWND owner,
	const std::stacktrace *trace)
{
	if (trace && !trace->empty())
		LOGGER_CRITICAL("{}\nstack trace:\n{}", wstr_to_utf8(text),
			std::to_string(*trace));
	else
		LOGGER_CRITICAL("{}", wstr_to_utf8(text));

	const std::wstring& log = logger::path();
	std::wstring body = text;
	while (!body.empty() && (body.back() == L'\n' || body.back() == L'\r'))
		body.pop_back();

	size_t nl = body.find(L'\n');
	std::wstring title = body.substr(0, nl);
	if (!title.empty() && title.back() == L'\r')
		title.pop_back();
	std::wstring details;
	if (nl != std::wstring::npos)
		details = body.substr(body.find_first_not_of(L"\r\n", nl));

	size_t cut = details.size();
	for (int n = 0; n < 25 && cut != 0; n++) {
		size_t pos = details.rfind(L'\n', cut - 1);
		cut = pos == std::wstring::npos ? 0 : pos;
	}
	if (cut != 0)
		cut++;
	if (details.size() - cut > 2000) {
		cut = details.size() - 2000;
		size_t pos = details.find(L'\n', cut);
		if (pos != std::wstring::npos)
			cut = pos + 1;
	}
	if (cut != 0)
		details = L"... (truncated, see log)\n" + details.substr(cut);

	std::wstring footer;
	if (!log.empty())
		footer = L"Log: <a href=\"" + log + L"\">" + log + L"</a>";

	TASKDIALOGCONFIG tdc = {};
	tdc.cbSize = sizeof(tdc);
	tdc.hwndParent = owner;
	tdc.dwFlags = TDF_ALLOW_DIALOG_CANCELLATION | TDF_ENABLE_HYPERLINKS;
	if (owner)
		tdc.dwFlags |= TDF_POSITION_RELATIVE_TO_WINDOW;
	tdc.dwCommonButtons = TDCBF_CLOSE_BUTTON;
	tdc.pszWindowTitle = L"Backpack";
	tdc.pszMainIcon = TD_ERROR_ICON;
	tdc.pszMainInstruction = title.c_str();
	if (!details.empty()) {
		tdc.pszExpandedInformation = details.c_str();
		tdc.pszCollapsedControlText = L"Show details";
		tdc.pszExpandedControlText = L"Hide details";
	}
	if (!footer.empty()) {
		tdc.pszFooterIcon = TD_INFORMATION_ICON;
		tdc.pszFooter = footer.c_str();
	}
	tdc.pfCallback = dialog_cb;

	if (FAILED(TaskDialogIndirect(&tdc, nullptr, nullptr, nullptr))) {
		std::wstring msg = title;
		if (!details.empty())
			msg += L"\n\n" + details;
		if (!log.empty())
			msg += L"\n\nLog: " + log;
		MessageBoxW(
			owner, msg.c_str(), L"Backpack", MB_OK | MB_ICONERROR);
	}
}
