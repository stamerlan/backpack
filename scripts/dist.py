import argparse
import os
import platform
import shutil
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


SRCTREE = Path(__file__).resolve().parent.parent


def app_version() -> str:
    try:
        return version("backpack")
    except PackageNotFoundError:
        return "0+unknown"

def platform_tag() -> str:
    system = {
        "win32": "windows",
        "darwin": "macos"
    }.get(
        sys.platform, sys.platform)
    arch = {
        "amd64": "x64",
        "x86_64": "x64",
        "arm64": "arm64",
        "aarch64": "arm64"
    }.get(platform.machine().lower(), platform.machine().lower())
    return f"{system}-{arch}"


def icon_path() -> Path | None:
    icons = SRCTREE / "ui" / "public" / "icons"
    match sys.platform:
        case "win32":
            path = icons / "app.ico"
        case "darwin":
            path = icons / "app.icns"
        case _:
            path = icons / "app.png"
    return path if path.is_file() else None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a standalone backpack package"
    )
    parser.add_argument(
        "--distpath", help="Where to put the bundled app", default="dist/"
    )
    parser.add_argument(
        "--workpath",
        help="Where to put all temporary files",
        default="build/"
    )
    parser.add_argument(
        "--entry",
        help="Entry script name",
        default=SRCTREE / "src" / "backpack" / "__main__.py"
    )
    parser.add_argument(
        "--name",
        help="Name to assign to the bundled app and spec file",
        default="backpack"
    )
    parser.add_argument(
        "--console",
        action="store_true",
        help="keep a console window for debugging (default windowed)",
    )
    args = parser.parse_args()

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name", args.name,
        "--distpath", args.distpath,
        "--workpath", args.workpath,
        "--specpath", args.workpath,
        "--paths", str(SRCTREE / "src"),
        "--add-data", f"{SRCTREE / "assets"}{os.pathsep}assets",
        # Compiled gettext catalogs (.mo) live under locales/; ship the tree so
        # locales_dir() can find them at runtime. Run "make locales" first.
        "--add-data", f"{SRCTREE / "locales"}{os.pathsep}locales",
        # pywebview loads its native backend and, on Windows, the bundled
        # WebView2 loader at runtime, so pull in the whole package.
        "--collect-all", "webview",
        # pydantic-ai and its dependencies read their own distribution metadata
        # at import time, which PyInstaller drops unless asked to copy it for
        # the whole tree.
        "--recursive-copy-metadata", "pydantic-ai-slim",
    ]
    cmd.append("--console" if args.console else "--windowed")
    if (icon := icon_path()) is not None:
        cmd += ["--icon", str(icon)]
    cmd.append(args.entry)

    subprocess.run(cmd, check=True)

    # make an archive
    ar_basename = f"{args.name}-{app_version()}-{platform_tag()}"
    distpath = Path(args.distpath)
    if sys.platform == "darwin":
        # A .app carries symlinks, exec bits and a code signature that a
        # plain zip drops, leaving macOS to reject the bundle as damaged.
        # ditto preserves all of it.
        app = Path(args.distpath) / f"{args.name}.app"
        subprocess.run(
            [
                "ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                str(app), str(distpath / (ar_basename + ".zip"))
            ],
            check=True
        )
    else:
        filename = args.name + (".exe" if sys.platform == "win32" else "")
        shutil.make_archive(
            str(distpath / ar_basename), "zip", distpath, filename
        )

if __name__ == "__main__":
    main()
