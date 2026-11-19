#ifndef WINDOW_H
#define WINDOW_H

#include <stdint.h>
#include <string>

#include <windows.h>

typedef struct _object PyObject;

class window_t {
public:
	window_t(HWND hwnd, ATOM atom) noexcept;
	~window_t(void);

	window_t(const window_t&) = delete;
	window_t &operator=(const window_t&) = delete;

	HWND hwnd(void) const noexcept { return handle; }

	void set_title(const std::wstring& title) const noexcept;
	void show(void) const noexcept;
	void hide(void) const noexcept;
	void fill(HDC dc, uint32_t rgb) const noexcept;

	/* Apply the theme. mode is "light", "dark" or "system" */
	void set_theme(const std::wstring& mode) noexcept;
	bool is_system_theme(void) const noexcept;
	bool is_dark_theme(void) const noexcept;

	/* New reference to a new Python object (native.win32.Window) borrowing
	 * this window, or nullptr with a Python error set. Requires the GIL.
	 */
	PyObject *to_py(void);
private:
	HWND handle = nullptr;
	ATOM atom = 0;

	struct {
		bool sys;
		bool dark;
	} theme = { true, false };
};

#endif /* WINDOW_H */
