import argparse
import shutil
import subprocess
import sys
import venv
from pathlib import Path


SRCTREE = Path(__file__).resolve().parent.parent


def shell(*cmd: object, cwd: str | Path | None = None) -> None:
    subprocess.run([str(x) for x in cmd], check=True, cwd=cwd)


def main() -> None:
    parser = argparse.ArgumentParser("Setup virtual environment")
    parser.add_argument("ENV_DIR", nargs="?", default=".venv")
    parser.add_argument("--extra", default="dev")
    args = parser.parse_args()

    env_dir = Path(args.ENV_DIR)
    if not env_dir.exists():
        venv.EnvBuilder(with_pip=True).create(env_dir)

    if sys.platform == "win32":
        py = str(env_dir / "Scripts" / "python.exe")
    else:
        py = str(env_dir / "bin" / "python")

    shell(py, "-m", "pip", "install", "--upgrade", "pip")
    shell(py, "-m", "pip", "install", "--editable",
        str(SRCTREE) + ("" if not args.extra else f"[{args.extra}]")
    )

if __name__ == "__main__":
    main()
