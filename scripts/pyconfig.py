"""Write build configuration as an MSBuild property sheet.

build.bat runs this with the build interpreter before msbuild, so the native
host compiles and links against that exact CPython. The generated .props file
is imported by backpack.vcxproj.

sys.base_prefix (not sys.prefix) is used so a build venv resolves to the base
install that actually ships the headers and the import library.
"""

import sys
from importlib.metadata import version
from pathlib import Path
from textwrap import dedent
from xml.sax.saxutils import escape


def main() -> None:
    AppVersion = version("backpack")
    PythonIncludeDir = rf"{sys.base_prefix}\include"
    PythonLibsDir = rf"{sys.base_prefix}\libs"
    PythonLib = f"python{sys.version_info.major}{sys.version_info.minor}.lib"
    PythonVersion = f"{sys.version_info.major}.{sys.version_info.minor}"

    out = Path(sys.argv[1])
    out.write_text(dedent(f"""\
        <?xml version="1.0" encoding="utf-8"?>
        <Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
          <PropertyGroup>
            <AppVersion>{escape(AppVersion)}</AppVersion>
            <PythonIncludeDir>{escape(PythonIncludeDir)}</PythonIncludeDir>
            <PythonLibsDir>{escape(PythonLibsDir)}</PythonLibsDir>
            <PythonLib>{escape(PythonLib)}</PythonLib>
            <PythonVersion>{escape(PythonVersion)}</PythonVersion>
          </PropertyGroup>
        </Project>
        """),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
