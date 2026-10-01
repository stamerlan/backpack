#ifndef LOGGER_H
#define LOGGER_H

#include <chrono>
#include <format>
#include <source_location>
#include <string>
#include <string_view>
#include <type_traits>
#include <utility>

namespace logger {

/* Python-compatible numeric levels */
enum level_t : int {
	DEBUG_LEVEL = 10,
	INFO_LEVEL = 20,
	WARNING_LEVEL = 30,
	ERROR_LEVEL = 40,
	CRITICAL_LEVEL = 50,
};

void init(int level) noexcept;
void close(void) noexcept;
int level(void) noexcept;
bool enabled(int level) noexcept;
const std::wstring& path(void) noexcept;

/* Format and write one record. Thread safe. name/func/msg are UTF-8. */
void write(int msg_level, std::string_view logger_name,
	std::string_view caller_func, std::string_view msg) noexcept;

/* Format and write one native record as "<file>:<line>: <func>: <msg>".
 * Thread safe. msg is UTF-8.
 */
void write(int msg_level, const std::source_location& loc,
	std::string_view msg) noexcept;

/* Format string checked at compile time, with the location of the call */
template <typename... Args>
struct format_t {
	std::format_string<Args...> fmt;
	std::source_location loc;

	template <typename S>
	consteval format_t(const S& s,
		std::source_location loc = std::source_location::current()
	) : fmt(s), loc(loc)
	{
	}
};

template <typename... Args>
void log(int level, format_t<std::type_identity_t<Args>...> f,
	Args&&... args) noexcept
try {
	if (!enabled(level))
		return;
	write(level, f.loc, std::format(f.fmt, std::forward<Args>(args)...));
} catch (...) {
}

template <typename... Args>
void debug(format_t<std::type_identity_t<Args>...> f, Args&&... args) noexcept
{
	log(DEBUG_LEVEL, f, std::forward<Args>(args)...);
}

template <typename... Args>
void info(format_t<std::type_identity_t<Args>...> f, Args&&... args) noexcept
{
	log(INFO_LEVEL, f, std::forward<Args>(args)...);
}

template <typename... Args>
void warning(format_t<std::type_identity_t<Args>...> f, Args&&... args) noexcept
{
	log(WARNING_LEVEL, f, std::forward<Args>(args)...);
}

template <typename... Args>
void error(format_t<std::type_identity_t<Args>...> f, Args&&... args) noexcept
{
	log(ERROR_LEVEL, f, std::forward<Args>(args)...);
}

template <typename... Args>
void critical(
	format_t<std::type_identity_t<Args>...> f, Args&&... args) noexcept
{
	log(CRITICAL_LEVEL, f, std::forward<Args>(args)...);
}

class timer_t {
public:
	timer_t(const char *what, int level = DEBUG_LEVEL,
		std::source_location loc = std::source_location::current()
	) noexcept;
	~timer_t(void);

	timer_t(const timer_t&) = delete;
	timer_t &operator=(const timer_t&) = delete;

	/* Log the elapsed time. Later calls do nothing. */
	void stop(void) noexcept;

private:
	const char *what;
	int level;
	std::source_location loc;
	std::chrono::steady_clock::time_point start;
	int exceptions;
	bool stopped = false;
};

} /* namespace logger */

#endif /* LOGGER_H */
