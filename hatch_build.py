import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class NpmBuildHook(BuildHookInterface):
    """Build the frontend and add it to the wheel.

    assets/ is generated, so it cannot be declared as a static
    force-include: it does not exist in a fresh clone. The hook builds it
    first and only then hands it to the builder.

    Editable installs are skipped: the developer builds the frontend
    with npm as a separate step and assets_dir() finds it in the source
    tree.
    """

    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if version == "editable":
            return

        root = Path(self.root)
        ui = root / "ui"
        assets = root / "assets"
        locales = root / "locales"

        # An sdist ships ui/, a tree with prebuilt assets may not
        if ui.is_dir():
            npm = shutil.which("npm")
            if npm is None:
                raise RuntimeError("npm is required to build the frontend")
            subprocess.run([npm, "ci"], cwd=ui, check=True)
            subprocess.run([npm, "run", "build"], cwd=ui, check=True)

        if not (assets / "index.html").is_file():
            raise RuntimeError(f"no built frontend at {assets}")

        build_data["force_include"][str(assets)] = "backpack/assets"

        if locales.is_dir():
            subprocess.run(
                [
                    sys.executable, "-m", "babel.messages.frontend",
                    "compile", "-d", str(locales), "-D", "backpack",
                ],
                check=True
            )
            build_data["force_include"][str(locales)] = "backpack/locales"
