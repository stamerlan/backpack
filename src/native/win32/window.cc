#include "window.h"
#include <dwmapi.h>

#pragma comment(lib, "dwmapi.lib")

/* Read the OS "apps" theme so a "system" choice resolves to dark or light.
 * Defaults to light when the key is missing.
 */
static bool is_system_dark_theme(void) noexcept
{
	HKEY key;
	LONG rc = RegOpenKeyExW(HKEY_CURRENT_USER,
		L"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize",
		0, KEY_QUERY_VALUE, &key);
	if (rc != ERROR_SUCCESS)
		return false;

	DWORD value = 1;
	DWORD size = sizeof(value);
	DWORD type = REG_DWORD;
	rc = RegQueryValueExW(key, L"AppsUseLightTheme", nullptr, &type,
		reinterpret_cast<LPBYTE>(&value), &size);
	RegCloseKey(key);
	if (rc != ERROR_SUCCESS || type != REG_DWORD)
		return false;
	return value == 0;
}

window_t::window_t(HWND hwnd, ATOM atom) noexcept
	: handle(hwnd), atom(atom)
{
}

window_t::~window_t(void)
{
	if (handle)
		DestroyWindow(handle);
	if (atom)
		UnregisterClassW(MAKEINTATOM(atom), GetModuleHandleW(nullptr));
}

void window_t::set_title(const std::wstring& title) const noexcept
{
	if (!handle)
		return;
	SetWindowTextW(handle, title.c_str());
}

void window_t::show(void) const noexcept
{
	if (!handle)
		return;
	ShowWindow(handle, SW_SHOWNORMAL);
	UpdateWindow(handle);
}

void window_t::hide(void) const noexcept
{
	if (!handle)
		return;
	ShowWindow(handle, SW_HIDE);
}

void window_t::set_theme(const std::wstring& mode) const noexcept
{
	if (!handle)
		return;

	bool dark = mode == L"dark" ||
		(mode != L"light" && is_system_dark_theme());
	BOOL is_dark = dark ? TRUE : FALSE;

	/* The immersive dark mode attribute is 20 on Windows 10 20H1 and later;
	 * the pre-20H1 value 19 is tried when 20 is rejected. The system
	 * backdrop is matched to the title bar material, as pywebview did.
	 */
	constexpr DWORD DWMWA_USE_IMMERSIVE_DARK_MODE = 20;
	constexpr DWORD DWMWA_USE_IMMERSIVE_DARK_MODE_PRE_20H1 = 19;
	constexpr DWORD DWMWA_SYSTEMBACKDROP_TYPE = 38;
	constexpr int DWMSBT_NONE = 1;
	constexpr int DWMSBT_MAINWINDOW = 2;

	HRESULT hr = DwmSetWindowAttribute(handle,
		DWMWA_USE_IMMERSIVE_DARK_MODE, &is_dark, sizeof(is_dark));
	if (FAILED(hr))
		DwmSetWindowAttribute(handle,
			DWMWA_USE_IMMERSIVE_DARK_MODE_PRE_20H1,
			&is_dark, sizeof(is_dark));

	int backdrop = dark ? DWMSBT_MAINWINDOW : DWMSBT_NONE;
	DwmSetWindowAttribute(handle, DWMWA_SYSTEMBACKDROP_TYPE,
		&backdrop, sizeof(backdrop));
}
