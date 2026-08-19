@echo off
setlocal

rem Run the test suites. With no arguments it runs every suite. Pass one or more
rem suite names (pytest, vitest) to run just those, in order.
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "PATH=%ROOT%\bin\node_modules\.bin;%PATH%"
set "NODE_PATH=%ROOT%\bin\node_modules"

set "ARCH=x64"
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "ARCH=arm64"
set "OUTDIR=%ROOT%\bin\windows-%ARCH%"
if not exist "%OUTDIR%" mkdir "%OUTDIR%"

set "VENV=%OUTDIR%\.venv"
set "PYTHON=%VENV%\Scripts\python.exe"

rem No suite named -> run them all
if "%~1"=="" (
  call :pytest || exit /b 1
  call :vitest || exit /b 1
  exit /b 0
)

rem Reject unknown suites before running any
for %%a in (%*) do (
  if /i not "%%a"=="pytest" if /i not "%%a"=="vitest" (
    echo Unknown argument: %%a 1>&2
    exit /b 2
  )
)

rem Run named suites in order. Each :name is a subroutine
for %%a in (%*) do call :%%a || exit /b 1
exit /b 0

:pytest
rem Python tests (also type checks via pytest-mypy)
call :venv || exit /b 1
call :run "%PYTHON%" -m pytest --junitxml="%OUTDIR%\pytest-report.xml" ^
  || exit /b 1
exit /b 0

:vitest
rem Frontend tests via vitest
if not exist "%ROOT%\bin" mkdir "%ROOT%\bin"
copy /y "%ROOT%\src\ui\package.json" "%ROOT%\bin\package.json" >nul
copy /y "%ROOT%\src\ui\package-lock.json" "%ROOT%\bin\package-lock.json" >nul
call :run npm --prefix "%ROOT%\bin" install || exit /b 1
call :run npm --prefix "%ROOT%\bin" exec -- vitest run ^
  --config "%ROOT%\src\ui\vite.config.ts" ^
  --reporter=default --reporter=junit ^
  --outputFile.junit="%OUTDIR%\vitest-report.xml" || exit /b 1
exit /b 0

rem Ensure the build venv exists with the package installed
:venv
if not exist "%PYTHON%" goto venvmake
"%PYTHON%" -c "pass" >nul 2>&1 && exit /b 0
:venvmake
if exist "%VENV%" rmdir /s /q "%VENV%"
call :run python -m venv "%VENV%" || exit /b 1
call :run "%PYTHON%" -m pip install --upgrade pip || exit /b 1
call :run "%PYTHON%" -m pip install --editable "%ROOT%[dev]" || exit /b 1
exit /b 0

:run
echo + %*
call %*
exit /b %errorlevel%
