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
	: handle(hwnd), atom(atom), theme{ true, is_system_dark_theme() }
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

void window_t::fill(HDC dc, uint32_t rgb) const noexcept
{
	RECT rect;
	COLORREF color = RGB(rgb >> 16 & 0xFF, rgb >> 8 & 0xFF, rgb & 0xFF);

	GetClientRect(handle, &rect);
	SetDCBrushColor(dc, color);
	FillRect(dc, &rect, static_cast<HBRUSH>(GetStockObject(DC_BRUSH)));
}

void window_t::set_theme(const std::wstring& mode) noexcept
{
	if (!handle)
		return;

	if (mode == L"dark") {
		theme.dark = true;
		theme.sys = false;
	} else if (mode == L"light") {
		theme.dark = false;
		theme.sys = false;
	} else {
		theme.dark = is_system_dark_theme();
		theme.sys = true;
	}

	BOOL is_dark = theme.dark ? TRUE : FALSE;

	/* The immersive dark mode attribute is 20 on Windows 10 20H1 and later.
	 * The pre-20H1 value 19 is tried when 20 is rejected.
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

	int backdrop = is_dark ? DWMSBT_MAINWINDOW : DWMSBT_NONE;
	DwmSetWindowAttribute(handle, DWMWA_SYSTEMBACKDROP_TYPE,
		&backdrop, sizeof(backdrop));

	InvalidateRect(handle, nullptr, TRUE);
}

bool window_t::is_system_theme(void) const noexcept
{
	return theme.sys;
}

bool window_t::is_dark_theme(void) const noexcept
{
	return theme.dark;
}
