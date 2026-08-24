#ifndef WINDOW_H
#define WINDOW_H

#include <string>

#include <windows.h>

class Window {
public:
	Window(void) = default;
	~Window(void);

	Window(const Window &) = delete;
	Window &operator=(const Window &) = delete;

	/* Register the window class with the host-supplied WndProc and create a
	 * top-level window whose client area is width by height. The param
	 * pointer is forwarded through CreateWindowEx as lpCreateParams so the
	 * host can stash its context during WM_NCCREATE.
	 */
	void create(const std::wstring& title, int width, int height,
		WNDPROC proc, void *param);

	HWND hwnd(void) const noexcept { return hwnd_; }

	void set_title(const std::wstring& title) const noexcept;
private:
	HWND hwnd_ = nullptr;
	HINSTANCE inst_ = nullptr;
	ATOM atom_ = 0;
};

#endif /* WINDOW_H */
