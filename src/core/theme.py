import logging
import sys
from typing import Any
import webview

logger = logging.getLogger(__name__)


class Theme:
    """Keep the native window title bar in sync with the app theme.

    The web content is themed by the frontend, but the title bar is native OS
    chrome drawn outside the document. On Windows pywebview only ever follows
    the OS theme, so an explicit light or dark choice is applied here and
    re-applied when the OS theme changes, so the bar never drifts out of sync.
    On macOS the native window appearance is set instead, which themes the
    title bar and follows the system on its own for the "system" mode, so no
    OS change hook is needed. Other platforms are a no-op.
    """

    def __init__(self, window: webview.Window | None = None) -> None:
        self._window = window
        self._theme = "system"
        self._hook_set = False

    def apply(self, mode: str) -> None:
        """Apply a theme mode and start following OS theme changes."""
        if self._window is None:
            return

        self._theme = mode

        if sys.platform == "darwin":
            _darwin_apply_theme(self._window, self._theme)
            return

        if sys.platform == "win32":
            _win32_apply_theme(self._window, self._theme)

            try:
                from Microsoft.Win32 import SystemEvents
                SystemEvents.UserPreferenceChanged += self._on_pref_changed
            except Exception:
                logger.exception("could not add system theme hook")
                return
            self._hook_set = True

    def close(self) -> None:
        """Stop following OS theme changes. Safe to call more than once."""
        if sys.platform != "win32" or not self._hook_set:
            return
        try:
            from Microsoft.Win32 import SystemEvents
            SystemEvents.UserPreferenceChanged -= self._on_pref_changed
            self._hook_set = False
        except Exception:
            logger.exception("could not remove system theme hook")

    def _on_pref_changed(self, _sender: object, _args: object) -> None:
        # pywebview re-applies the system theme on this event, so re-apply the
        # chosen mode afterwards to keep an explicit light or dark choice.
        _win32_apply_theme(self._window, self._theme)


def _win32_apply_theme(window: webview.Window | None, theme: str) -> None:
    if sys.platform != "win32" or window is None:
        return

    import ctypes
    from ctypes import wintypes
    import winreg

    try:
        native: Any = window.native
        if native is None:
            return
        hwnd = native.Handle.ToInt32()
    except Exception:
        logger.exception("native window handle unavailable")
        return

    try:
        if theme not in ("dark", "light"):
            # get system theme
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
                ) as key:
                    value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                theme = "dark" if int(value) == 0 else "light"
            except OSError:
                theme = "light"

        is_dark = 1 if theme == "dark" else 0

        # Toggle the DWM dark title bar for a window handle.
        #
        # The immersive dark mode attribute is 20 on Windows 10 20H1 and later;
        # the pre-20H1 name 19 is tried when 20 is rejected. The system backdrop
        # is set to match the title bar material to the theme the way
        # pywebview does.
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        DWMWA_USE_IMMERSIVE_DARK_MODE_PRE_20H1 = 19
        DWMWA_SYSTEMBACKDROP_TYPE = 38
        DWMSBT_MAINWINDOW = 2
        DWMSBT_NONE = 1

        dwm = ctypes.windll.dwmapi.DwmSetWindowAttribute
        dwm.argtypes = [
            wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
        ]
        def set_window_attr(attr: int, value: int) -> int:
            data = ctypes.c_int(value)
            return int(dwm(hwnd, attr, ctypes.byref(data), ctypes.sizeof(data)))

        if set_window_attr(DWMWA_USE_IMMERSIVE_DARK_MODE, is_dark) != 0:
            set_window_attr(DWMWA_USE_IMMERSIVE_DARK_MODE_PRE_20H1, is_dark)
        set_window_attr(
            DWMWA_SYSTEMBACKDROP_TYPE,
            DWMSBT_MAINWINDOW if is_dark else DWMSBT_NONE,
        )
    except OSError:
        logger.exception("native title bar theming failed")


def _darwin_apply_theme(window: webview.Window | None, theme: str) -> None:
    if sys.platform != "darwin" or window is None:
        return

    try:
        import AppKit
        from PyObjCTools import AppHelper
    except Exception:
        logger.exception("AppKit unavailable")
        return

    try:
        native: Any = window.native
        if native is None:
            return
    except Exception:
        logger.exception("native window unavailable")
        return

    # A named appearance forces the whole window chrome, title bar included, to
    # the chosen theme. A nil appearance lets the window follow the system and
    # keep tracking later OS theme changes on its own, so "system" needs no
    # explicit hook the way Windows does.
    if theme == "dark":
        name = AppKit.NSAppearanceNameDarkAqua
    elif theme == "light":
        name = AppKit.NSAppearanceNameAqua
    else:
        name = None

    def apply() -> None:
        try:
            appearance = (
                AppKit.NSAppearance.appearanceNamed_(name)
                if name is not None else None
            )
            native.setAppearance_(appearance)
        except Exception:
            logger.exception("native title bar theming failed")

    # AppKit must be touched on the main thread, but set_theme runs on the
    # asyncio loop thread, so hand the change to the Cocoa run loop.
    AppHelper.callAfter(apply)
