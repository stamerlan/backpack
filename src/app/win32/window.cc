#include "window.h"

#include "winerr.h"

static const wchar_t *const window_class_name = L"BackpackWindow";

void Window::create(const std::wstring& title, int width, int height,
	WNDPROC proc, void *param)
{
	inst_ = GetModuleHandleW(nullptr);

	WNDCLASSEXW wc = {};
	wc.cbSize = sizeof(wc);
	wc.style = CS_HREDRAW | CS_VREDRAW;
	wc.lpfnWndProc = proc;
	wc.hInstance = inst_;
	wc.hCursor = LoadCursorW(nullptr, IDC_ARROW);
	wc.lpszClassName = window_class_name;

	atom_ = RegisterClassExW(&wc);
	if (atom_ == 0) {
		DWORD err = GetLastError();
		if (err != ERROR_CLASS_ALREADY_EXISTS)
			throw Winerr(err, "RegisterClassExW() failed");
	}

	RECT rect = { 0, 0, width, height };
	AdjustWindowRectEx(&rect, WS_OVERLAPPEDWINDOW, FALSE, 0);

	hwnd_ = CreateWindowExW(
		0, window_class_name, title.c_str(), WS_OVERLAPPEDWINDOW,
		CW_USEDEFAULT, CW_USEDEFAULT,
		rect.right - rect.left, rect.bottom - rect.top,
		nullptr, nullptr, inst_, param);
	if (hwnd_ == nullptr)
		throw Winerr("CreateWindowExW() failed");
}

Window::~Window(void)
{
	if (hwnd_)
		DestroyWindow(hwnd_);
	if (atom_)
		UnregisterClassW(window_class_name, inst_);
}

void Window::set_title(const std::wstring& title) const noexcept
{
	if (!hwnd_)
		return;
	SetWindowTextW(hwnd_, title.c_str());
}
