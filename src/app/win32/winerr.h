#ifndef WINERR_H
#define WINERR_H

#include <format>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>

#include <windows.h>

#include "utf8.h"

inline std::wstring get_err_str(DWORD code, DWORD lang = 0)
{
	LPWSTR raw = nullptr;
	DWORD len = FormatMessageW(
		FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM
			| FORMAT_MESSAGE_IGNORE_INSERTS,
		nullptr, code, lang, reinterpret_cast<LPWSTR>(&raw), 0, nullptr
	);
	std::unique_ptr<wchar_t, decltype(&LocalFree)> buffer(raw, LocalFree);
	while (len && (raw[len - 1] == L'\r' || raw[len - 1] == L'\n'))
		--len;
	return len ? std::wstring(raw, len) : std::wstring();
}

class Winerr : public std::runtime_error {
public:
	template <class... Args>
	explicit Winerr(
		DWORD code, std::format_string<Args...> fmt = "", Args &&...args
	)
		: std::runtime_error(
			fmt_errmsg(code, fmt, std::forward<Args>(args)...)
		)
		, code_(code)
	{
	}

	template <class... Args>
	explicit Winerr(std::format_string<Args...> fmt, Args &&...args)
		: Winerr(GetLastError(), fmt, std::forward<Args>(args)...)
	{
	}

	DWORD code(void) const noexcept { return code_; }

private:
	template <class... Args>
	static std::string fmt_errmsg(
		DWORD code, std::format_string<Args...> fmt, Args &&...args)
	{
		std::string msg = std::format(fmt, std::forward<Args>(args)...);
		std::wstring err_str = get_err_str(code);
		if (!err_str.empty()) {
			if (!msg.empty())
				msg += ": ";
			msg += wstr_to_utf8(err_str);
		}
		return msg + std::format(" (0x{:08X})", code);
	}

	DWORD code_;
};

#endif /* WINERR_H */
