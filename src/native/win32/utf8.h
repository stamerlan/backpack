#ifndef UTF8_H
#define UTF8_H

#include <windows.h>

#include <string>
#include <string_view>

inline std::wstring utf8_to_wstr(std::string_view utf8)
{
	if (utf8.empty())
		return {};

	int len = MultiByteToWideChar(
		CP_UTF8, 0, utf8.data(), static_cast<int>(utf8.size()),
		nullptr, 0);

	std::wstring wstr(static_cast<size_t>(len), L'\0');
	MultiByteToWideChar(
		CP_UTF8, 0, utf8.data(), static_cast<int>(utf8.size()),
		wstr.data(), len);
	return wstr;
}

inline std::string wstr_to_utf8(std::wstring_view wstr)
{
	if (wstr.empty())
		return {};

	int len = WideCharToMultiByte(
		CP_UTF8, 0, wstr.data(), static_cast<int>(wstr.size()),
		nullptr, 0, nullptr, nullptr);

	std::string utf8(static_cast<size_t>(len), '\0');
	WideCharToMultiByte(
		CP_UTF8, 0, wstr.data(), static_cast<int>(wstr.size()),
		utf8.data(), len, nullptr, nullptr);
	return utf8;
}

#endif /* UTF8_H */