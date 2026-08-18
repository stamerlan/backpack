@ECHO OFF

REM Activate the Visual Studio developer environment so msbuild and the VC
REM toolchain are on PATH.

IF DEFINED VSDEVCMD IF EXIST "%VSDEVCMD%" GOTO run

SETLOCAL
SET "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
IF NOT EXIST "%VSWHERE%" ( ECHO No vswhere found 1>&2 & EXIT /B 1 )

FOR /F "usebackq tokens=*" %%I IN (`"%VSWHERE%" -latest -products * ^
    -requires Microsoft.Component.MSBuild ^
    -property installationPath`) DO SET "VSROOT=%%I"
IF NOT DEFINED VSROOT ( ECHO No Visual Studio found 1>&2 & EXIT /B 1 )
ENDLOCAL & SET "VSDEVCMD=%VSROOT%\Common7\Tools\VsDevCmd.bat"

:run
CALL "%VSDEVCMD%" %*
