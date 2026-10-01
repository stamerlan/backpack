#ifndef LOGGER_H
#define LOGGER_H

#include <chrono>
#include <format>
#include <mutex>
#include <source_location>
#include <string>
#include <string_view>
#include <type_traits>
#include <utility>
#include <windows.h>

class logger_t {
public:
	/* Python-compatible numeric levels */
	enum level_t : int {
		DEBUG_LEVEL = 10,
		INFO_LEVEL = 20,
		WARNING_LEVEL = 30,
		ERROR_LEVEL = 40,
		CRITICAL_LEVEL = 50,
	};

	template <typename... Args>
	struct format_t {
		std::format_string<Args...> fmt;
		std::source_location loc;

		template <typename S>
		consteval format_t(const S& s,
			std::source_location loc =
				std::source_location::current()
		) : fmt(s), loc(loc)
		{
		}
	};

	logger_t(const logger_t&) = delete;
	logger_t &operator=(const logger_t&) = delete;

	static logger_t& instance(void) noexcept;

	static void open(int level) noexcept;
	static void close(void) noexcept;
	static int level(void) noexcept;
	static bool enabled(int level) noexcept;
	static const std::wstring& path(void) noexcept;

	/* Format and write one record. Thread safe. name/func/msg are
	 * UTF-8.
	 */
	static void write(int msg_level, std::string_view logger_name,
		std::string_view caller_func, std::string_view msg) noexcept;

	/* Format and write one native record as
	 * "<file>:<line>: <func>: <msg>". Thread safe. msg is UTF-8.
	 */
	static void write(int msg_level, const std::source_location& loc,
		std::string_view msg) noexcept;

	template <typename... Args>
	static void log(int level, format_t<std::type_identity_t<Args>...> f,
		Args&&... args) noexcept
	try {
		if (!enabled(level))
			return;
		write(level, f.loc,
			std::format(f.fmt, std::forward<Args>(args)...));
	} catch (...) {
	}

	template <typename... Args>
	static void debug(format_t<std::type_identity_t<Args>...> f,
		Args&&... args) noexcept
	{
		log(DEBUG_LEVEL, f, std::forward<Args>(args)...);
	}

	template <typename... Args>
	static void info(format_t<std::type_identity_t<Args>...> f,
		Args&&... args) noexcept
	{
		log(INFO_LEVEL, f, std::forward<Args>(args)...);
	}

	template <typename... Args>
	static void warning(format_t<std::type_identity_t<Args>...> f,
		Args&&... args) noexcept
	{
		log(WARNING_LEVEL, f, std::forward<Args>(args)...);
	}

	template <typename... Args>
	static void error(format_t<std::type_identity_t<Args>...> f,
		Args&&... args) noexcept
	{
		log(ERROR_LEVEL, f, std::forward<Args>(args)...);
	}

	template <typename... Args>
	static void critical(format_t<std::type_identity_t<Args>...> f,
		Args&&... args) noexcept
	{
		log(CRITICAL_LEVEL, f, std::forward<Args>(args)...);
	}

private:
	/* Output callbacks. An output that is not open uses the *_none
	 * pair.
	 */
	using write_fn = void (*)(HANDLE h, const std::string& s);
	using close_fn = void (*)(HANDLE h);

	logger_t(void) noexcept;
	~logger_t(void);

	void do_open(int level) noexcept;
	void do_close(void) noexcept;
	void write_line(int level, std::string_view source,
		std::string_view msg) noexcept;

	std::mutex mut;
	int logger_level = INFO_LEVEL;

	/* log file */
	HANDLE file = INVALID_HANDLE_VALUE;
	write_fn file_write;
	close_fn file_close;
	std::wstring log_path;

	/* Terminal handle.
	 * The handle might be a redirected or inherited stderr (not ours to
	 * close), or CONOUT$ of the parent console
	 */
	HANDLE term = INVALID_HANDLE_VALUE;
	write_fn term_write;
	close_fn term_close;

	/* process creation on the monotonic clock, for the elapsed field */
	std::chrono::steady_clock::time_point start_tp;
};

using logger = logger_t;

#endif /* LOGGER_H */
