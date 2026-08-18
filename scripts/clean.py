import shutil
from itertools import chain
from pathlib import Path

SRCTREE = Path(__file__).resolve().parent.parent

def rm(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.is_file():
        path.unlink()


def main() -> None:
    for name in chain(
        (
            "__pycache__/",
            ".mypy_cache/",
            ".pytest_cache/",
            "assets/",
            "bin/",
            "build/",
            "dist/",
            "src/ui/node_modules/",
            "src/backpack/_version.py",
            "pytest-report.xml",
            "src/ui/vitest-report.xml",
        ),
        SRCTREE.glob("*.spec"),
        SRCTREE.glob("*.egg-info"),
        (SRCTREE / "src").rglob("*.egg-info"),
        (SRCTREE / "src").rglob("__pycache__"),
        (SRCTREE / "tests").rglob("__pycache__"),
        (SRCTREE / "scripts").rglob("__pycache__"),
    ):
        rm(SRCTREE / name)


if __name__ == "__main__":
    main()
