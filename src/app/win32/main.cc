#include <string>

#include <windows.h>
#include <objbase.h>

#include "app.h"
#include "utf8.h"
#include "winerr.h"

static std::wstring get_module_dir(void)
{
	std::wstring path(MAX_PATH, L'\0');
	for (;;) {
		DWORD path_size = static_cast<DWORD>(path.size());
		DWORD n = GetModuleFileNameW(nullptr, path.data(), path_size);
		if (n == 0)
			throw Winerr("GetModuleFileNameW() failed");
		if (n < path_size) {
			path.resize(n);
			break;
		}
		path.resize(path_size * 2);
	}
	size_t slash = path.find_last_of(L"\\/");
	if (slash != std::wstring::npos)
		path.resize(slash);
	return path;
}

/* Turn a Windows path into a file:// URL WebView2 can navigate to.
 * Backslashes become forward slashes and spaces are percent-encoded so a
 * path under a profile directory with a space still resolves.
 */
static std::wstring to_file_url(const std::wstring& path)
{
	std::wstring url = L"file:///";
	for (wchar_t c : path) {
		switch (c) {
		case L'\\':
			url += L'/';
			break;
		case L' ':
			url += L"%20";
			break;
		default:
			url += c;
			break;
		}
	}
	return url;
}

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int)
try {
	HRESULT hr = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
	if (FAILED(hr))
		throw Winerr(hr, "CoInitializeEx() failed");

	std::wstring app_dir = get_module_dir();
	std::wstring url = to_file_url(app_dir + L"\\assets\\index.html");

	App app(url);
	app.create(L"Backpack", 1200, 800);
	app.window().show();

	MSG m = {};
	while (GetMessageW(&m, nullptr, 0, 0) > 0) {
		TranslateMessage(&m);
		DispatchMessageW(&m);
	}

	CoUninitialize();
	return static_cast<int>(m.wParam);
} catch (const std::exception& e) {
	MessageBoxW(nullptr, utf8_to_wstr(e.what()).c_str(), L"Backpack",
		MB_OK | MB_ICONERROR);
	return 1;
}
