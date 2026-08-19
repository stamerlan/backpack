"""Tests for core.paths - filesystem location helpers."""
from pathlib import Path
from unittest.mock import patch

from core import APP_NAME
from core.paths import applogs


class TestApplogs:
    def test_windows_uses_localappdata(self) -> None:
        with patch("core.paths.sys.platform", "win32"), patch.dict(
            "os.environ", {"LOCALAPPDATA": "C:/Local"}, clear=True
        ), patch("core.paths.Path.home", return_value=Path("C:/home")):
            assert applogs() == Path("C:/Local") / APP_NAME / "Logs"

    def test_windows_falls_back_to_home(self) -> None:
        home = Path("C:/Users/tester")
        with patch("core.paths.sys.platform", "win32"), patch.dict(
            "os.environ", {}, clear=True
        ), patch("core.paths.Path.home", return_value=home):
            assert applogs() == home / "AppData/Local" / APP_NAME / "Logs"

    def test_macos_uses_library_logs(self) -> None:
        home = Path("/Users/tester")
        with patch("core.paths.sys.platform", "darwin"), patch(
            "core.paths.Path.home", return_value=home
        ):
            assert applogs() == home / "Library/Logs" / APP_NAME

    def test_linux_uses_xdg_state_home(self) -> None:
        with patch("core.paths.sys.platform", "linux"), patch.dict(
            "os.environ", {"XDG_STATE_HOME": "/xdg/state"}, clear=True
        ), patch("core.paths.Path.home", return_value=Path("/home/x")):
            assert applogs() == Path("/xdg/state") / APP_NAME

    def test_linux_falls_back_to_local_state(self) -> None:
        home = Path("/home/tester")
        with patch("core.paths.sys.platform", "linux"), patch.dict(
            "os.environ", {}, clear=True
        ), patch("core.paths.Path.home", return_value=home):
            assert applogs() == home / ".local/state" / APP_NAME

    def test_does_not_create_directory(self) -> None:
        with patch("core.paths.sys.platform", "darwin"), patch(
            "core.paths.Path.home", return_value=Path("/Users/tester")
        ):
            assert not applogs().exists()
