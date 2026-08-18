"""Zip a PyInstaller onedir build into a versioned archive."""
import os
import shutil
import sys
from importlib.metadata import version


def main() -> None:
    dist, osarch = sys.argv[1:3]
    ver = version("backpack")
    outdir = os.path.dirname(os.path.normpath(dist))
    shutil.make_archive(
        f"{outdir}/backpack-{ver}-{osarch}", "zip", dist, "backpack"
    )


if __name__ == "__main__":
    main()
