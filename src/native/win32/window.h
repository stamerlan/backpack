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

	/* Apply the theme. mode is "light", "dark" or "system" */
	void set_theme(std::wstring mode) noexcept;
	bool is_system_theme(void) const noexcept;
private:
	HWND handle = nullptr;
	ATOM atom = 0;
	std::wstring theme;
};

#endif /* WINDOW_H */
