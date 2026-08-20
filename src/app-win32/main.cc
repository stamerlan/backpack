#include <memory>
#include <string>

#include <windows.h>
#include <shellapi.h>

#include <Python.h>

#include "pyconfig.h"
#include "utf8.h"
#include "winerr.h"

static std::wstring get_module_dir(void)
{
	std::wstring path(MAX_PATH, L'\0');
	for (;;) {
		DWORD path_size = static_cast<DWORD>(path.size());
		DWORD n = GetModuleFileNameW(nullptr, path.data(), path_size);
		if (n == 0)
			throw winerr("GetModuleFileNameW() failed");
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

static void show_error_msg(const std::wstring& text)
{
	MessageBoxW(nullptr, text.c_str(), L"Backpack", MB_OK | MB_ICONERROR);
}

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int)
try {
	std::wstring app_dir = get_module_dir();

	pyconfig_t config;
	config.set_parse_argv(0);
	config.set_program_name(app_dir.c_str());
	config.set_home(app_dir.c_str());
	config.set_run_module(L"core");
	config.add_module_search_path(app_dir.c_str());
	config.add_module_search_path((app_dir + L"\\lib").c_str());

	int argc = 0;
	std::unique_ptr<LPWSTR, decltype(&LocalFree)> argv(
		CommandLineToArgvW(GetCommandLineW(), &argc), &LocalFree);
	if (argv)
		config.set_argv(argc, argv.get());

	config.init();
	return Py_RunMain();
} catch (const PyStatus& status) {
	std::wstring msg(L"Python error");
	if (status.err_msg) {
		msg += L"\n\n";
		msg += utf8_to_wstr(status.err_msg);
	}
	show_error_msg(msg);
	return 1;
} catch (const std::exception& e) {
	show_error_msg(utf8_to_wstr(e.what()));
	return 1;
}
