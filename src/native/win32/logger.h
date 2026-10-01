#ifndef LOGGER_H
#define LOGGER_H

#include <chrono>
#include <format>
#include <optional>
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

/* Format and write one record of a Python logger as
 * "<name>::<func>(): <msg>". Thread safe. name/func/msg are UTF-8.
 */
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
	consteval format_t(const S& s, std::source_location loc =
		std::source_location::current())
		: fmt(s), loc(loc)
	{
	}
};

/* Log a native record. The arguments are always evaluated like any function
 * arguments, the message is formatted only if level is enabled. Formatting
 * errors are swallowed.
 */
template <typename... Args>
void log(int level, format_t<std::type_identity_t<Args>...> f,
	Args&&... args) noexcept
{
	if (!enabled(level))
		return;
	try {
		write(level, f.loc, std::format(f.fmt,
			std::forward<Args>(args)...));
	} catch (...) {
	}
}

template <typename... Args>
void debug(format_t<std::type_identity_t<Args>...> f,
	Args&&... args) noexcept
{
	log(DEBUG_LEVEL, f, std::forward<Args>(args)...);
}

template <typename... Args>
void info(format_t<std::type_identity_t<Args>...> f,
	Args&&... args) noexcept
{
	log(INFO_LEVEL, f, std::forward<Args>(args)...);
}

template <typename... Args>
void warning(format_t<std::type_identity_t<Args>...> f,
	Args&&... args) noexcept
{
	log(WARNING_LEVEL, f, std::forward<Args>(args)...);
}

template <typename... Args>
void error(format_t<std::type_identity_t<Args>...> f,
	Args&&... args) noexcept
{
	log(ERROR_LEVEL, f, std::forward<Args>(args)...);
}

template <typename... Args>
void critical(format_t<std::type_identity_t<Args>...> f,
	Args&&... args) noexcept
{
	log(CRITICAL_LEVEL, f, std::forward<Args>(args)...);
}

/* Stopwatch that logs "<what>: <ms> ms" at level when destroyed, if it was
 * started. what must outlive the object.
 *
 * Usually used through LOGGER_DURATION.
 */
class duration_t {
public:
	duration_t(const char *what, int level = DEBUG_LEVEL,
		std::source_location loc =
			std::source_location::current()) noexcept;
	/* Stops a running stopwatch, then logs */
	~duration_t(void);

	duration_t(const duration_t&) = delete;
	duration_t &operator=(const duration_t&) = delete;

	/* Start the stopwatch on the first call and return true. Stop it on
	 * the next call and return false. Later calls return false and keep
	 * the first measurement.
	 */
	bool toggle(void) noexcept;

private:
	const char *what;
	int level;
	std::source_location loc;
	std::optional<std::chrono::steady_clock::time_point> start;
	std::optional<std::chrono::steady_clock::duration> elapsed;
};

} /* namespace logger */

#define LOGGER_CAT_(a, b) a##b
#define LOGGER_CAT(a, b) LOGGER_CAT_(a, b)

/* Time the statement (or block) that follows and log "<what>: <ms> ms":
 *
 *	LOGGER_DURATION("COM init")
 *		hr = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
 *	LOGGER_DURATION("window creation", logger::INFO_LEVEL) { ... }
 *
 * The level is optional, DEBUG by default. The body runs once inside a
 * hidden for loop, so break and continue end the timed body itself, not an
 * enclosing loop.
 */
#define LOGGER_DURATION(...) \
	for (::logger::duration_t LOGGER_CAT(logger_duration_, \
		__LINE__)(__VA_ARGS__); \
		LOGGER_CAT(logger_duration_, __LINE__).toggle();)

#endif /* LOGGER_H */
