#ifndef PY_CONFIG_H
#define PY_CONFIG_H

#include <Python.h>

/* Create a configuration to isolate Python from the system.
 *
 * This configuration ignores global configuration variables, environment
 * variables, command line arguments (PyConfig.argv is not parsed) and user site
 * directory. The C standard streams (ex: stdout) and the LC_CTYPE locale are
 * left unchanged. Signal handlers are not installed.
 */
class pyconfig_t {
public:
	pyconfig_t(void) { PyConfig_InitIsolatedConfig(&cfg); }
	~pyconfig_t(void) { PyConfig_Clear(&cfg); }

	pyconfig_t(const pyconfig_t &) = delete;
	pyconfig_t &operator=(const pyconfig_t &) = delete;

	PyConfig *get(void) noexcept { return &cfg; }

	void init(void)
	{
		PyStatus status = Py_InitializeFromConfig(&cfg);
		if (PyStatus_Exception(status))
			throw status;
	}

	/* Program name used to initialize the executable search path and shown
	 * in early error messages during interpreter startup.
	 */
	void set_program_name(const wchar_t *name)
	{
		PyStatus status = PyConfig_SetString(
			&cfg, &cfg.program_name, name);
		if (PyStatus_Exception(status))
			throw status;
	}

	/* Python "home" directory: the base used to locate the standard library
	 * and to compute sys.prefix and sys.exec_prefix.
	 */
	void set_home(const wchar_t *home)
	{
		PyStatus status = PyConfig_SetString(&cfg, &cfg.home, home);
		if (PyStatus_Exception(status))
			throw status;
	}

	/* Module executed as __main__, equivalent to the -m command line option
	 * (the app runs "core").
	 */
	void set_run_module(const wchar_t *module)
	{
		PyStatus status = PyConfig_SetString(
			&cfg, &cfg.run_module, module);
		if (PyStatus_Exception(status))
			throw status;
	}

	/* Non-zero makes startup parse argv like the regular python launcher
	 * and strip the options it consumes; zero leaves argv untouched.
	 */
	void set_parse_argv(int enabled) noexcept
	{
		cfg.parse_argv = enabled;
	}

	/* Append one sys.path entry and mark module_search_paths_set so the
	 * list is used verbatim and the default path calculation is skipped.
	 */
	void add_module_search_path(const wchar_t *path)
	{
		cfg.module_search_paths_set = 1;
		PyStatus status = PyWideStringList_Append(
			&cfg.module_search_paths, path);
		if (PyStatus_Exception(status))
			throw status;
	}

	/* Interpreter sys.argv. With parse_argv zero it is passed through
	 * unchanged; argv[0] conventionally names the running program.
	 */
	void set_argv(Py_ssize_t argc, wchar_t *const *argv)
	{
		PyStatus status = PyConfig_SetArgv(&cfg, argc, argv);
		if (PyStatus_Exception(status))
			throw status;
	}

private:
	PyConfig cfg;
};

#endif /* PY_CONFIG_H */
