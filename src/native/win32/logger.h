#ifndef LOGGER_H
#define LOGGER_H

#include <chrono>
#include <format>
#include <optional>
#include <string>
#include <string_view>

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

/* Stopwatch that logs "<what>: <ms> ms" at level when destroyed, if it was
 * started. func and what must outlive the object.
 *
 * Usually used through LOGGER_DURATION.
 */
class duration_t {
public:
	duration_t(const char *func, const char *what,
		int level = DEBUG_LEVEL) noexcept;
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
	const char *func;
	const char *what;
	int level;
	std::optional<std::chrono::steady_clock::time_point> start;
	std::optional<std::chrono::steady_clock::duration> elapsed;
};

} /* namespace logger */

/* Log a native record if level is enabled. The format call never throws out
 * of the macro.
 */
#define LOGGER_LOG(level, ...) \
	do { \
		if (::logger::enabled(level)) { \
			try { \
				::logger::write(level, "win32", __func__, \
					std::format(__VA_ARGS__)); \
			} catch (...) { \
			} \
		} \
	} while (0)

#define LOGGER_DEBUG(...) LOGGER_LOG(::logger::DEBUG_LEVEL, __VA_ARGS__)
#define LOGGER_INFO(...) LOGGER_LOG(::logger::INFO_LEVEL, __VA_ARGS__)
#define LOGGER_WARNING(...) LOGGER_LOG(::logger::WARNING_LEVEL, __VA_ARGS__)
#define LOGGER_ERROR(...) LOGGER_LOG(::logger::ERROR_LEVEL, __VA_ARGS__)
#define LOGGER_CRITICAL(...) \
	LOGGER_LOG(::logger::CRITICAL_LEVEL, __VA_ARGS__)

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
		__LINE__)(__func__, __VA_ARGS__); \
		LOGGER_CAT(logger_duration_, __LINE__).toggle();)

#endif /* LOGGER_H */
