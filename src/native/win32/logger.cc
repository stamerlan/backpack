#include "logger.h"

#include <algorithm>
#include <chrono>
#include <format>
#include <functional>
#include <mutex>
#include <string>
#include <string_view>
#include <vector>

#include <windows.h>
#include <knownfolders.h>
#include <shlobj.h>

#include "utf8.h"

/* The real Windows version. GetVersionExW reports 6.2 to apps without a
 * supportedOS manifest entry. Declared in the WDK only.
 */
extern "C" NTSYSAPI LONG NTAPI RtlGetVersion(PRTL_OSVERSIONINFOW info);
#pragma comment(lib, "ntdll.lib")

namespace logger {

/* Retention (D1), counting the current run */
static constexpr size_t logs_keep = 10;

static ULONGLONG to_u64(FILETIME ft)
{
	return (static_cast<ULONGLONG>(ft.dwHighDateTime) << 32)
		| ft.dwLowDateTime;
}

/* Output callbacks. An output that is not open uses the *_none pair. */
using write_fn = void (*)(HANDLE h, const std::string& s);
using close_fn = void (*)(HANDLE h);

static void write_none(HANDLE, const std::string&)
{
}

/* UTF-8 bytes, for a file, a pipe or NUL */
static void write_bytes(HANDLE h, const std::string& s)
{
	DWORD n;
	WriteFile(h, s.data(), static_cast<DWORD>(s.size()), &n, nullptr);
}

/* UTF-16, for a real console */
static void write_console(HANDLE h, const std::string& s)
{
	DWORD n;
	std::wstring ws = utf8_to_wstr(s);
	WriteConsoleW(h, ws.data(), static_cast<DWORD>(ws.size()), &n, nullptr);
}

static void close_none(HANDLE)
{
}

static void close_handle(HANDLE h)
{
	CloseHandle(h);
}

/* CONOUT$ of the parent console attached in init */
static void close_console(HANDLE h)
{
	CloseHandle(h);
	FreeConsole();
}

/* The process wide logger behind the logger:: functions */
class logger_t {
public:
	logger_t(void) = default;
	~logger_t(void) { close(); }

	logger_t(const logger_t&) = delete;
	logger_t &operator=(const logger_t&) = delete;

	void init(int level) noexcept;
	void close(void) noexcept;
	int level(void) const noexcept { return logger_level; }
	bool enabled(int level) const noexcept { return level >= logger_level; }
	const std::wstring& path(void) const noexcept { return log_path; }
	void write(int level, std::string_view name, std::string_view func,
		std::string_view msg) noexcept;

private:
	std::mutex mut;
	int logger_level = INFO_LEVEL;

	/* log file */
	HANDLE file = INVALID_HANDLE_VALUE;
	write_fn file_write = write_none;
	close_fn file_close = close_none;
	std::wstring log_path;

	/* Terminal handle.
	 * The handle might be a redirected or inherited stderr (not ours to
	 * close), or CONOUT$ of the parent console
	 */
	HANDLE term = INVALID_HANDLE_VALUE;
	write_fn term_write = write_none;
	close_fn term_close = close_none;

	/* process creation on the monotonic clock, for the elapsed field */
	std::chrono::steady_clock::time_point start_tp;
};

void logger_t::init(int level) noexcept
try {
	close();

	logger_level = level;

	/* Only the time from process creation to now is taken from the wall
	 * clock, the elapsed field then follows the monotonic clock
	 */
	std::chrono::nanoseconds since{};
	FILETIME creation, exited, kern, user, now;
	GetSystemTimePreciseAsFileTime(&now);
	if (GetProcessTimes(
		GetCurrentProcess(), &creation, &exited, &kern, &user
	) && to_u64(creation) < to_u64(now))
		since = std::chrono::nanoseconds(
			(to_u64(now) - to_u64(creation)) * 100);
	start_tp = std::chrono::steady_clock::now() - since;

	HANDLE h = GetStdHandle(STD_ERROR_HANDLE);
	DWORD h_type = FILE_TYPE_UNKNOWN;
	if (h != NULL && h != INVALID_HANDLE_VALUE)
		h_type = GetFileType(h);

	if (h_type == FILE_TYPE_DISK || h_type == FILE_TYPE_CHAR
		|| h_type == FILE_TYPE_PIPE) {
		term = h;
	} else if (AttachConsole(ATTACH_PARENT_PROCESS)) {
		term = CreateFileW(L"CONOUT$", GENERIC_READ | GENERIC_WRITE,
			FILE_SHARE_WRITE, nullptr, OPEN_EXISTING, 0, nullptr);
		if (term != INVALID_HANDLE_VALUE)
			term_close = close_console;
		else
			FreeConsole();
	}

	/* A real console is written as UTF-16, anything else (a file, a pipe,
	 * NUL) gets the UTF-8 bytes
	 */
	DWORD mode;
	if (term != INVALID_HANDLE_VALUE)
		term_write = GetConsoleMode(term, &mode) ?
			write_console : write_bytes;

	/* This run's log file in %LOCALAPPDATA%\Backpack\Logs */
	PWSTR base = nullptr;
	std::wstring log_dir;
	HRESULT hr = SHGetKnownFolderPath(
		FOLDERID_LocalAppData, 0, nullptr, &base);
	if (SUCCEEDED(hr))
		log_dir = std::wstring(base) + L"\\Backpack";
	CoTaskMemFree(base);

	if (!log_dir.empty()) {
		CreateDirectoryW(log_dir.c_str(), nullptr);
		log_dir += L"\\Logs";
		CreateDirectoryW(log_dir.c_str(), nullptr);

		SYSTEMTIME t;
		GetLocalTime(&t);
		std::wstring p = std::format(
			L"{}\\backpack-{:04}{:02}{:02}-{:02}{:02}{:02}-{}.log",
			log_dir, t.wYear, t.wMonth, t.wDay, t.wHour,
			t.wMinute, t.wSecond, GetCurrentProcessId());
		file = CreateFileW(p.c_str(), FILE_APPEND_DATA,
			FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, CREATE_NEW,
			FILE_ATTRIBUTE_NORMAL, nullptr);
		if (file != INVALID_HANDLE_VALUE) {
			log_path = std::move(p);
			file_write = write_bytes;
			file_close = close_handle;
		}

		/* Delete the oldest backpack-*.log files beyond logs_keep.
		 * File names start with a timestamp, so name order is age
		 * order. Failures are ignored.
		 */
		std::vector<std::wstring> names;
		WIN32_FIND_DATAW fd;
		HANDLE find = FindFirstFileW(
			(log_dir + L"\\backpack-*.log").c_str(), &fd);
		if (find != INVALID_HANDLE_VALUE) {
			do {
				/* short 8.3 names let "*.log" match longer
				 * extensions
				 */
				std::wstring_view name(fd.cFileName);
				bool is_dir = fd.dwFileAttributes
					& FILE_ATTRIBUTE_DIRECTORY;
				if (!is_dir && name.ends_with(L".log"))
					names.emplace_back(name);
			} while (FindNextFileW(find, &fd));
			FindClose(find);
		}

		std::sort(names.begin(), names.end(), std::greater<>());
		for (size_t i = logs_keep; i < names.size(); i++) {
			std::wstring p = log_dir + L"\\" + names[i];
			if (p != log_path)
				DeleteFileW(p.c_str());
		}
	}

	/* The first lines: executable, PID, command line, Windows build */
	std::wstring exe(MAX_PATH, L'\0');
	for (;;) {
		DWORD size = static_cast<DWORD>(exe.size());
		DWORD n = GetModuleFileNameW(nullptr, exe.data(), size);
		if (n < size) {
			exe.resize(n);
			break;
		}
		exe.resize(size * 2);
	}

	RTL_OSVERSIONINFOW ver = {};
	ver.dwOSVersionInfoSize = sizeof(ver);
	RtlGetVersion(&ver);

	LOGGER_INFO("{} (pid {})", wstr_to_utf8(exe), GetCurrentProcessId());
	LOGGER_INFO("command line: {}", wstr_to_utf8(GetCommandLineW()));
	LOGGER_INFO("Windows {}.{}.{}", ver.dwMajorVersion,
		ver.dwMinorVersion, ver.dwBuildNumber);
	LOGGER_INFO("log level {}, log file: {}", logger_level,
		log_path.empty() ? "none" : wstr_to_utf8(log_path));
} catch (...) {
	/* keep running with whatever got opened */
}

void logger_t::close(void) noexcept
{
	std::lock_guard lock(mut);
	file_close(file);
	term_close(term);

	file = INVALID_HANDLE_VALUE;
	file_write = write_none;
	file_close = close_none;
	term = INVALID_HANDLE_VALUE;
	term_write = write_none;
	term_close = close_none;
}

void logger_t::write(int msg_level, std::string_view logger_name,
	std::string_view caller_func, std::string_view msg) noexcept
try {
	if (msg_level < logger_level)
		return;

	auto elapsed_ms =
		std::chrono::duration_cast<std::chrono::milliseconds>(
			std::chrono::steady_clock::now() - start_tp
		).count();

	FILETIME now, local;
	GetSystemTimePreciseAsFileTime(&now);
	SYSTEMTIME t;
	FileTimeToLocalFileTime(&now, &local);
	FileTimeToSystemTime(&local, &t);
	ULONGLONG us = to_u64(local) % 10000000 / 10;

	char letter = msg_level >= CRITICAL_LEVEL ? 'C' :
		msg_level >= ERROR_LEVEL ? 'E' :
		msg_level >= WARNING_LEVEL ? 'W' :
		msg_level >= INFO_LEVEL ? 'I' : 'D';

	std::string line = std::format(
		"{:02}:{:02}:{:02}.{:06} +{}.{:03} {} {} ",
		t.wHour, t.wMinute, t.wSecond, us, elapsed_ms / 1000,
		elapsed_ms % 1000, GetCurrentThreadId(), letter);
	line += logger_name;
	if (!caller_func.empty()) {
		if (!logger_name.empty())
			line += "::";
		line += caller_func;
		line += "()";
	}
	line += ": ";
	line += msg;
	line += '\n';

	std::lock_guard lock(mut);
	file_write(file, line);
	term_write(term, line);
} catch (...) {
	/* a log call never throws */
}

static logger_t instance;

void init(int level) noexcept
{
	instance.init(level);
}

void close(void) noexcept
{
	instance.close();
}

int level(void) noexcept
{
	return instance.level();
}

bool enabled(int level) noexcept
{
	return instance.enabled(level);
}

const std::wstring& path(void) noexcept
{
	return instance.path();
}

void write(int msg_level, std::string_view logger_name,
	std::string_view caller_func, std::string_view msg) noexcept
{
	instance.write(msg_level, logger_name, caller_func, msg);
}

duration_t::duration_t(const char *func, const char *what, int level) noexcept
	: func(func), what(what), level(level)
{
}

duration_t::~duration_t(void)
{
	if (!start)
		return;
	toggle();
	if (!enabled(level))
		return;
	std::chrono::duration<double, std::milli> ms = *elapsed;
	try {
		write(level, "win32", func,
			std::format("{}: {:.1f} ms", what, ms.count()));
	} catch (...) {
	}
}

bool duration_t::toggle(void) noexcept
{
	auto now = std::chrono::steady_clock::now();
	if (start == std::nullopt) {
		start = now;
		return true;
	}
	if (elapsed == std::nullopt)
		elapsed = now - *start;
	return false;
}

} /* namespace logger */
