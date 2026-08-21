@echo off
setlocal

rem Build the app. Without arguments it compiles the frontend assets, the
rem message catalogs, the native Windows host (Release), and assembles the
rem runnable bundle next to backpack.exe. Pass --debug for a debug build, and
rem --app to also pack the bundle into a distributable zip.

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "PATH=%ROOT%\bin\node_modules\.bin;%PATH%"
set "NODE_PATH=%ROOT%\bin\node_modules"

set "CONFIG=Release"
set "APP=0"

:parse
if "%~1"=="" goto build
if /i "%~1"=="--app" (
  set "APP=1"
  shift
  goto parse
)
if /i "%~1"=="--debug" (
  set "CONFIG=Debug"
  shift
  goto parse
)
echo Unknown argument: %~1 1>&2
exit /b 2

:build

set "ARCH=x64"
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "ARCH=arm64"
set "OSARCH=windows-%ARCH%"
set "OUTDIR=%ROOT%\bin\%OSARCH%"

rem Build owned virtual environment under the arch output dir, holding the
rem package and its tools. It keeps builds independent of a preinstalled
rem environment and is wiped by clean.bat with the rest of bin\.
set "VENV=%OUTDIR%\.venv"
set "PYTHON=%VENV%\Scripts\python.exe"
call :venv || exit /b 1
set "PATH=%VENV%\Scripts;%PATH%"

rem Frontend assets into bin\assets
if not exist "%ROOT%\bin" mkdir "%ROOT%\bin"
copy /y "%ROOT%\src\ui\package.json" "%ROOT%\bin\package.json" >nul
copy /y "%ROOT%\src\ui\package-lock.json" "%ROOT%\bin\package-lock.json" >nul
call :run npm --prefix "%ROOT%\bin" install || exit /b 1
call :run npm --prefix "%ROOT%\bin" exec -- tsc --noEmit -p "%ROOT%\src\ui" ^
  || exit /b 1
call :run npm --prefix "%ROOT%\bin" exec -- vite build ^
  --config "%ROOT%\src\ui\vite.config.ts" || exit /b 1

rem Message catalogs into bin\locales
if exist "%ROOT%\bin\locales" rmdir /s /q "%ROOT%\bin\locales"
xcopy /e /i /q /y "%ROOT%\locales" "%ROOT%\bin\locales" >nul || exit /b 1
call :run pybabel compile -d "%ROOT%\bin\locales" -D backpack || exit /b 1

rem Generate build settings
call :run "%PYTHON%" "%ROOT%\scripts\pyconfig.py" "%OUTDIR%\pyconfig.props" ^
  || exit /b 1

rem Native Windows host
call :run msbuild "%ROOT%\src\app-win32\backpack.slnx" -maxCpuCount ^
  -property:Configuration=%CONFIG% -property:Platform=x64 || exit /b 1

rem With --app also pack the app into a versioned distributable zip
set "ARCHIVE="
if "%APP%"=="1" call :setarchive
call :run "%PYTHON%" "%ROOT%\scripts\winbundle.py" "%OUTDIR%" "%ROOT%" ^
  %ARCHIVE% || exit /b 1
exit /b 0

rem Compose the --archive argument for winbundle from the package version.
:setarchive
for /f "delims=" %%v in (
  'python -c "import core;print(core.APP_VERSION)"'
) do (
  set ARCHIVE=--archive "%OUTDIR%\backpack-%%v-%OSARCH%.zip"
)
exit /b 0

rem Ensure the build venv exists with the package installed. A valid venv is
rem reused for fast rebuilds; an unusable one (e.g. left by a container build
rem whose C:\src paths do not resolve on the host) is recreated.
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
