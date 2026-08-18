"""Zip a PyInstaller onedir build into a versioned archive."""
import shutil
import sys
from importlib.metadata import version


def main() -> None:
    dist, osarch = sys.argv[1:3]
    ver = version("backpack")
    shutil.make_archive(
        f"{dist}/backpack-{ver}-{osarch}", "zip", dist, "backpack"
    )


if __name__ == "__main__":
    main()
