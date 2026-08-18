@echo off
setlocal

rem Build the app. Without arguments it compiles the frontend assets,
rem the message catalogs, and the native Windows host (Release). Pass --debug
rem for a debug build, and --app to also produce the distributable package.

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "PYTHON=python"
set "PATH=%ROOT%\bin\node_modules\.bin;%PATH%"
set "NODE_PATH=%ROOT%\bin\node_modules"

set "CONFIG=Release"
set "WINDOW=--windowed"
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
  set "WINDOW=--console"
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

rem Native Windows host
call :run msbuild "%ROOT%\src\app-win32\backpack.slnx" -maxCpuCount ^
  -property:Configuration=%CONFIG% -property:Platform=x64 || exit /b 1

if not "%APP%"=="1" exit /b 0

rem Standalone PyInstaller distributable + zip
call :run "%PYTHON%" -m PyInstaller --noconfirm --clean --onedir ^
  --contents-directory app --name backpack ^
  --distpath "%OUTDIR%\dist" --workpath "%OUTDIR%\build" ^
  --specpath "%OUTDIR%\build" --paths "%ROOT%\src" ^
  --add-data "%ROOT%\bin\assets;assets" ^
  --add-data "%ROOT%\bin\locales;locales" ^
  --collect-all webview ^
  --recursive-copy-metadata pydantic-ai-slim ^
  --exclude-module setuptools ^
  --exclude-module pkg_resources ^
  --exclude-module pip ^
  --icon "%ROOT%\src\ui\public\icons\app.ico" ^
  %WINDOW% ^
  "%ROOT%\src\backpack\__main__.py" || exit /b 1
call :run "%PYTHON%" "%ROOT%\scripts\mkzip.py" "%OUTDIR%\dist" "%OSARCH%" ^
  || exit /b 1
exit /b 0

:run
echo + %*
call %*
exit /b %errorlevel%
