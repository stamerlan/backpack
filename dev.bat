@echo off
setlocal

rem Serve the frontend with hot reload. Run the app in a second terminal with
rem "python -m app.win32 --dev" to point it at this dev server.

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "PATH=%ROOT%\bin\node_modules\.bin;%PATH%"
set "NODE_PATH=%ROOT%\bin\node_modules"

if not exist "%ROOT%\bin" mkdir "%ROOT%\bin"
copy /y "%ROOT%\src\ui\package.json" "%ROOT%\bin\package.json" >nul
copy /y "%ROOT%\src\ui\package-lock.json" "%ROOT%\bin\package-lock.json" >nul
call :run npm --prefix "%ROOT%\bin" install || exit /b 1
call :run npm --prefix "%ROOT%\bin" exec -- vite ^
  --config "%ROOT%\src\ui\vite.config.ts" || exit /b 1
exit /b 0

:run
echo + %*
call %*
exit /b %errorlevel%
