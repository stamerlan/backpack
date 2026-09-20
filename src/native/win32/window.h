#ifndef WINDOW_H
#define WINDOW_H

#include <string>

#include <windows.h>

class window_t {
public:
	window_t(HWND hwnd, ATOM atom) noexcept;
	~window_t(void);

	window_t(const window_t &) = delete;
	window_t &operator=(const window_t &) = delete;

	HWND hwnd(void) const noexcept { return handle; }

	void set_title(const std::wstring& title) const noexcept;
	void show(void) const noexcept;
	void hide(void) const noexcept;

	/* Store and apply the theme. mode is "light", "dark" or "system"
	 * (otherwise same as system). Runs on the UI thread.
	 */
	void set_theme(const std::wstring& mode) noexcept;

	/* Re-apply the stored theme, a no-op until set_theme has run once. The
	 * host calls this on WM_SETTINGCHANGE so a "system" title bar follows the
	 * OS and an explicit choice is not reset. Runs on the UI thread.
	 */
	void reapply_theme(void) const noexcept;
private:
	void apply_theme(const std::wstring& mode) const noexcept;

	HWND handle = nullptr;
	ATOM atom = 0;
	std::wstring theme;
};

#endif /* WINDOW_H */
