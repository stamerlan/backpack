# Native logger (Windows)

Status: **design settled**. The current release covers the native logger and
Python logging only. Everything else is in section 7, for future releases.

Branch context: the work goes on top of `next` (base `master`) as new
commits, made by the user. History is not rewritten.


## 1. Problem

The Windows app is `backpack.exe`, a native C++ host
(`src/native/win32/main.cc`) that embeds CPython and runs `backpack.main` on a
worker thread. The exe has no console (`<SubSystem>Windows</SubSystem>`), and
until now logging was configured in Python only, inside `backpack.main`. So
nothing was logged before `backpack.main` ran (COM init, window and WebView2
creation, Python init), and startup could not be profiled.


## 2. Scope

This release:

1. The native code owns the log file from the first line of `wWinMain`.
2. Startup can be profiled from one timeline: each line carries the elapsed
   time since the process was created, and startup stages log their duration.
3. Fatal native errors are logged before the error dialog is shown.
4. When run from a terminal, log output is copied to it.
5. Python logging is routed into the same file.

Not in this release (section 7): crash dumps, Python stdout/stderr and
faulthandler capture, the host-provided log path for "Open logs", core thread
tracebacks, frontend logs and a native macOS logger.


## 3. Decisions

| # | Decision |
|---|----------|
| S1 | One shared log file per application start. Native and Python lines go to the same file. |
| S2 | File name: `%LOCALAPPDATA%\Backpack\Logs\backpack-YYYYMMDD-HHMMSS-PID.log` (local time). No rotation mid-run. |
| S3 | Retention: keep the newest 10 logs, counting the current run. Pruned at startup. |
| S4 | The log is copied to the terminal: a redirected stderr first, otherwise the parent console if there is one. |
| S5 | Name: **native logger**. Files are `logger.h/.cc`, `py/logger.cc` and `native/logger.py`. C++ identifiers live in `namespace logger`. Levels keep the `_LEVEL` suffix because `wingdi.h` defines an `ERROR` macro. |
| S6 | Line format: `time +elapsed tid L source: msg`, level letters `D I W E C` (5.2). |
| S7 | C++ API: free function templates (`logger::info("...", args)`), format checked at compile time, carrying `std::source_location`. A log call never throws. No macros: stage timings use `logger::timer_t`. |
| S8 | Fatal native errors go through `show_fatal` (`error_dialog.h`): log at CRITICAL, then a task dialog with a link to the log. |
| S9 | Startup milestones at INFO, `logger::timer_t` timings at DEBUG. |
| S10 | Python logging: the root logger gets a single handler that passes each record to the native sink. The level comes from the native logger (`-d`). `logging.captureWarnings(True)`. |
| S11 | Each host entry point configures logging; `backpack.main` doesn't. The macOS entry point takes over the old setup (console plus the rotating `backpack.log`, `-d`), so macOS behaves as before. On Windows the legacy `backpack.log` is no longer written. |
| S12 | No history rewrite. The user makes every commit. This document stays at `docs/native-logger.md`; the user commits it or drops it separately. |


## 4. Architecture

```
wWinMain
 +- parse argv (-d, --dev)
 +- logger::init(level)                 -> per-run log file, prune, console
 +- COM / window / webview              (milestones, timings)
 +- config.init()                       (python init)
 +- native.logger.install(sink)         <- Python root logger -> sink
 |     sink = py::logger_object()  -> logger::write(...)
 +- build_py_app -> py thread -> backpack.main
 `- exit code logged, logger::close()
```

The native logger is the single writer: it owns the file and console handles.
Python never opens the log; it calls the sink.


## 5. Native components (`src/native/win32`)

Code style: tabs (width 8), `/* */` comments, `(void)` for empty parameter
lists, lowercase `_t` type names, and `std::format`. Match `defer_call.h` and
`event_queue.h`. Add new files to `backpack.vcxproj`.

### 5.1 `logger.h` / `logger.cc` - done

`logger.h` is the reference. In short: `init`, `close`, `level`, `enabled`,
`path`, two `write` overloads (Python records and native records), the
`debug`..`critical` templates and `timer_t`. Writes are unbuffered,
one `WriteFile` per record under a mutex, so everything logged before a crash
survives. Errors inside the logger are swallowed.

### 5.2 Line format

```
14:30:12.123456 +0.182 1234 I main.cc:330: run: url:https://assets/
14:30:12.301002 +0.360 5678 W backpack.core::open(): could not read file
```

Local wall time with microseconds, `+seconds` since process creation, OS
thread id, level letter, then the source and the message. Native records use
`file:line: func(): message`. Python records use `name::func(): message`.

### 5.3 `py/logger.cc` (Python sink object)

`PyObject *py::logger_object(void)` in `py/object.h`, type
`native.win32.Logger`, built like `py/event_queue.cc`.

- `write(level: int, name: str, func: str, msg: str) -> None`: parse with
  `"is#s#s#"`, release the GIL around `logger::write`.
- `level: int`: read-only attribute, `logger::level()`.

### 5.4 `main.cc`

`install_py_logger()` runs right after `config.init()` and before
`build_py_app`, so records emitted while `backpack` is imported are captured.
It imports `native.logger` and calls `install(py::logger_object())`. On
failure it logs a warning and startup continues.


## 6. Python components

### 6.1 `src/native/logger.py` (stdlib only, must not import `backpack`)

```python
class Sink(Protocol):
    level: int                     # read-only
    def write(self, level: int, name: str, func: str, msg: str) -> None: ...

class SinkHandler(logging.Handler):
    # msg = Formatter("%(message)s").format(record)  (appends exc/stack text)
    # sink.write(record.levelno, record.name, record.funcName, msg)

def install(sink: Sink) -> None:
    # root.handlers[:] = [SinkHandler(sink)]; root.setLevel(sink.level)
    # logging.captureWarnings(True)
```

### 6.2 `src/backpack/main.py` and the macOS entry point

`LogFormatter`, the handler setup, the `-d` parsing and the `pywebview`
handler clearing move from `backpack.main` to `_setup_logging(debug)` in
`src/native/macos/__main__.py`, called right after its argument parsing
(S11). `backpack.main` keeps the third-party level overrides and the
`Starting ...` and `Exit` lines.

### 6.3 Tests

`tests/test_native_logger.py` with a fake sink: field mapping, exception
text, sink errors going to `handleError`, the `install` wiring, level
filtering and captured warnings. `pytest-mypy` type-checks the module.


## 7. Implementation plan

### Step 1: native logger - DONE

Committed as `add native logger to the Windows host`, `add an error dialog
to the Windows host` and `log startup steps in the Windows host`.

Notes: the debug build needs `python314_d.lib`, which is not installed on the
dev machine, so only the release build is verified.

### Step 2: `route python logging to the native logger`

1. `py/logger.cc` (5.3), declared in `py/object.h`, added to
   `backpack.vcxproj`.
2. `src/native/logger.py` (6.1) and `tests/test_native_logger.py` (6.3).
3. `install_py_logger()` in `main.cc` (5.4), timed with `logger::timer_t`.
4. Move the logging setup to the macOS entry point (6.2).
5. Run `test.bat pytest` and `build.bat`. Verify V1-V4 and, on a Mac,
   V5.

### Future releases

Each item is a separate small release. Notes from the earlier design are kept
so they don't have to be rediscovered.

- **Crash handler** (`crash.h/.cc`). `SetUnhandledExceptionFilter`,
  `std::set_terminate` and `SIGABRT`: write a `fatal:` line with a
  preformatted buffer and a direct `WriteFile`, then `MiniDumpNormal` next to
  the log (`.dmp`), keep the newest 5 dumps, link `Dbghelp.lib`. Return
  `EXCEPTION_CONTINUE_SEARCH` so WER still shows its dialog. Verify with
  temporary local edits only, no crash flag.
- **Python stdout/stderr and faulthandler.** `sys.stderr` to the log,
  `sys.stdout` to the console only (needs stdout resolution and
  `logger::write_stdout`). For C-level fd 2, Python opens the log in append
  mode and `os.dup2`s it, then enables `faulthandler`. That needs the log
  opened with `FILE_SHARE_WRITE` and the logger caching its console handles
  at init, since `dup2` replaces the process stderr handle.
- **Host-provided log path.** `AppHost.log_path` and `open_folder(path)`;
  the sink gets a `path` attribute and the native window an `open_folder`
  method (`ShellExecuteExW`). `Core.open_logs` opens `log_path.parent` and
  loses its platform branches.
- **Core thread failures.** Replace `PyErr_Print()` in the core thread with
  one fetch, a CRITICAL record with the full traceback, and `show_fatal` on
  the UI thread after the join. Exit code 1.
- **macOS native logger.** A native macOS sink with a per-run file and
  signal handlers. The system already writes `.ips` crash reports.
- **Frontend logs.** Capture console, `onerror` and `unhandledrejection` in
  `index.tsx`; on Windows `on_msg` writes them with `logger::write` directly.
  Rate-limited.


## 8. Verification (Windows)

| # | Scenario | Expected |
|---|----------|----------|
| V1 | Double-click `backpack.exe` | A new `backpack-<ts>-<pid>.log` appears with native and Python lines; the startup milestones have increasing `+elapsed` values |
| V2 | `backpack.exe -d 2>&1 \| Out-Host` from PowerShell | Log lines are copied to the terminal; native and Python DEBUG lines are present |
| V3 | `backpack.exe -d 2> err.txt` | `err.txt` holds the same lines as the log file |
| V4 | Any start | No new writes to the legacy `backpack.log` |
| V5 | macOS, from source with and without `-d` | Same as before: console output, `backpack.log` in `~/Library/Logs/Backpack`, DEBUG lines only with `-d` |


## 9. How agents should use this document

- Follow section 7 in order, one step at a time. Change only what that step
  describes, and verify with section 8.
- Stage the changes and stop. The user makes every commit. Never commit,
  push or force-push.
- If reality contradicts this document, stop, update the document and ask
  the user.
