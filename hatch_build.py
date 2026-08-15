import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class NpmBuildHook(BuildHookInterface):
    """Build the frontend and add it to the wheel.

    bin/assets is generated, so it cannot be declared as a static
    force-include: it does not exist in a fresh clone. The hook builds
    it first and only then hands it to the builder.

    Editable installs are skipped: the developer builds the frontend
    with make assets and assets_dir() finds it in the source tree.
    """

    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if version == "editable":
            return

        root = Path(self.root)
        bindir = root / "bin"
        bindir.mkdir(exist_ok=True)
        ui = root / "ui"
        assets = bindir / "assets"
        locales = root / "locales"

        # An sdist ships ui/, a tree with prebuilt assets may not
        if ui.is_dir():
            npm = shutil.which("npm")
            if npm is None:
                raise RuntimeError(
                    "npm is required to build the frontend"
                )
            shutil.copy2(ui / "package.json", bindir / "package.json")
            shutil.copy2(
                ui / "package-lock.json",
                bindir / "package-lock.json",
            )
            env = os.environ.copy()
            env["NODE_PATH"] = str(bindir / "node_modules")

            def run_npm(*args: str) -> None:
                subprocess.run(
                    [npm, *args], cwd=root, check=True, env=env
                )

            run_npm("--prefix", str(bindir), "ci")
            run_npm(
                "--prefix", str(bindir), "exec", "--",
                "tsc", "--noEmit", "-p", "ui",
            )
            run_npm(
                "--prefix", str(bindir), "exec", "--",
                "vite", "build",
                "--config", "ui/vite.config.ts",
            )

        if not (assets / "index.html").is_file():
            raise RuntimeError(f"no built frontend at {assets}")

        build_data["force_include"][str(assets)] = "backpack/assets"

        if locales.is_dir():
            dest = bindir / "locales"
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(locales, dest)
            subprocess.run(
                [
                    sys.executable, "-m", "babel.messages.frontend",
                    "compile", "-d", str(dest), "-D", "backpack",
                ],
                check=True
            )
            build_data["force_include"][str(dest)] = "backpack/locales"
