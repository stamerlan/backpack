"""Assemble the native Windows bundle.

Everything the launcher needs comes from sys.base_prefix, the base install
behind the interpreter running this script (the build venv). Because the native
host was compiled and linked against that same interpreter, the bundled python
DLL, extension modules and standard library always match the ABI backpack.exe
expects.

Assembled in place so backpack.exe runs straight from <bin>, and optionally
packed into a zip whose members sit under a single top-level directory.
"""
import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Assemble Windows bundle")
    parser.add_argument("bin", type=Path,
        help="directory holding backpack.exe, assembled in place"
    )
    parser.add_argument("project", type=Path, help="project root to install")
    parser.add_argument("--assets", type=Path,
        help="bundled frontend assets (default: {bin}/../assets)"
    )
    parser.add_argument("--locales", type=Path,
        help="bundled message catalogs (default: {bin}/../locales)"
    )
    parser.add_argument("--lib", default="lib",
        help="module subdirectory name (default: lib)"
    )
    parser.add_argument("--archive", type=Path,
        help="write a zip of the bundle to this path"
    )
    parser.add_argument("--name", default="backpack",
        help="top-level directory inside the archive (default: backpack)"
    )
    args = parser.parse_args()

    base = Path(sys.base_prefix)
    bin = args.bin
    lib = bin / args.lib
    assets = args.assets or bin.parent / "assets"
    locales = args.locales or bin.parent / "locales"
    pyver = f"{sys.version_info.major}{sys.version_info.minor}"

    # Interpreter DLLs that sit next to python.exe
    runtime = [f"python{pyver}.dll", "python3.dll"]
    runtime += [p.name for p in base.glob("vcruntime140*.dll")]
    for name in runtime:
        src = base / name
        if src.is_file():
            shutil.copy2(src, bin / name)

    # Extension modules and the DLLs they depend on, kept together under lib/.
    # Windows resolves a module's dependent DLLs from the module's own folder
    # first, so co-locating them there keeps bin/ to just the exe and the core
    # interpreter DLLs. Skip the icons and catalog that also ship in DLLs/, the
    # Tk GUI stack (the UI is WebView2), and the CPython self-test modules.
    lib.mkdir(parents=True, exist_ok=True)
    skip = ("_test", "_ctypes_test", "_tkinter", "tcl", "tk")
    for src in (base / "DLLs").iterdir():
        if src.suffix.lower() not in (".pyd", ".dll"):
            continue
        if src.stem.lower().startswith(skip):
            continue
        shutil.copy2(src, lib / src.name)

    # Standard library as plain source, sharing lib/ with third-party modules
    # so every import resolves from a single directory. Drop the packaging and
    # dev-only trees the app never imports at runtime
    shutil.copytree(
        base / "Lib", lib, dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(
            "site-packages", "test", "__pycache__",
            "idlelib", "ensurepip", "venv", "pydoc_data",
            "tkinter", "turtledemo", "turtle.py", "lib2to3",
        )
    )

    # Core package and its runtime dependencies
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--target", str(lib),
         str(args.project)],
        check=True)

    # pip leaves console-script launchers under bin/ that nothing invokes
    shutil.rmtree(lib / "bin", ignore_errors=True)

    # Babel bundles CLDR data for every locale; keep only the app's languages
    # (plus root and en that Babel falls back to) to save tens of megabytes
    locale_data = lib / "babel" / "locale-data"
    if locale_data.is_dir():
        langs = {"root", "en"}
        for p in locales.iterdir():
            if p.is_dir():
                langs.add(p.name.split("_")[0])
        for dat in locale_data.glob("*.dat"):
            if dat.stem.split("_")[0] not in langs:
                dat.unlink()

    # Bundled resources next to the exe; paths.py probes the core package
    # parents and finds them there. Only the compiled *.mo catalogs are used
    # at runtime, the *.po/*.pot sources stay behind as build inputs
    shutil.copytree(assets, bin / "assets", dirs_exist_ok=True)
    for mo in locales.rglob("*.mo"):
        dst = bin / "locales" / mo.relative_to(locales)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(mo, dst)
    for cache in lib.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)

    if not args.archive:
        return

    # Pack the distributable package
    members = [
        p for p in bin.iterdir()
        if p.is_file() and p.suffix.lower() in (".exe", ".dll", ".pyd")
    ]
    for sub in (args.lib, "assets", "locales"):
        members += [p for p in (bin / sub).rglob("*") if p.is_file()]
    with zipfile.ZipFile(args.archive, "w", zipfile.ZIP_DEFLATED) as f:
        for path in members:
            arc = Path(args.name) / path.relative_to(bin)
            f.write(path, arc.as_posix())


if __name__ == "__main__":
    main()
