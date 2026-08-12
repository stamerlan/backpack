"""Gettext i18n runtime backed by Babel."""
import sys
from collections.abc import Sequence
from gettext import NullTranslations

from babel.support import Translations

from . import APP_NAME
from .paths import locales_dir


SUPPORTED_LANG: tuple[str, ...] = ("en", "ru")


class I18n:
    """Loads Babel message catalogs and exposes gettext/ngettext.

    Message ids are the English source strings. A missing catalog or entry
    returns the English source unchanged
    (``Translations.load(..., fallback=True)`` semantics via NullTranslations).
    """

    def __init__(self) -> None:
        self._translations: NullTranslations = NullTranslations()
        self._lang: str = "en"
        self._tag: str = "en"
        self._units: str = "metric"

    @property
    def lang(self) -> str:
        """Base language subtag of the active locale, e.g. "en" or "ru"."""
        return self._lang

    @property
    def tag(self) -> str:
        """Full BCP-47 tag of the active locale, e.g. "en-GB" or "ru".

        Carries the region subtag when the preferred locale named one, so the
        frontend can format numbers and dates in the chosen dialect. Falls
        back to the bare language when no region is known.
        """
        return self._tag

    @property
    def units(self) -> str:
        """Default measurement system, "metric" or "imperial".

        Taken from the OS preference when available, otherwise from the
        preferred locale region (imperial for US, metric elsewhere).
        """
        return self._units

    def load(self, locale: str | Sequence[str]) -> None:
        """Negotiate locale against SUPPORTED and load the catalog.

        *locale* is a single BCP-47 tag or a sequence ordered by priority.
        An unrecognized tag negotiates to ``en``. A region subtag is kept in
        ``tag`` so the frontend can pick a dialect, and a matching regional
        catalog (``en_GB``) is loaded in preference to the base language
        (``en``) when one is present. Default units follow the OS preference,
        falling back to the region of the preferred locale.
        """
        if isinstance(locale, str):
            locale = [locale]
        self._lang, region = _pick_locale(locale)
        self._tag = f"{self._lang}-{region}" if region else self._lang
        self._units = system_units() or _get_region_units(region)
        names = (
            [f"{self._lang}_{region}", self._lang] if region
            else [self._lang]
        )
        self._translations = Translations.load(
            str(locales_dir()), names, APP_NAME
        )

    def gettext(self, message: str, /, **kwargs: object) -> str:
        """Translate *message* and format ``{name}`` placeholders.

        If formatting the translated string fails (bad placeholder), falls back
        to the English source string.
        """
        translated: str = self._translations.gettext(message)
        if not kwargs:
            return translated
        try:
            return translated.format_map(kwargs)
        except (KeyError, IndexError, ValueError):
            try:
                return message.format_map(kwargs)
            except (KeyError, IndexError, ValueError):
                return message

    def ngettext(
        self, singular: str, plural: str, n: int, /,
        **kwargs: object
    ) -> str:
        """Translate a plural message and format placeholders.

        ``{n}`` is always available in the format context. On a bad fill the raw
        English source form is returned.
        """
        translated: str = self._translations.ngettext(singular, plural, n)
        all_kwargs: dict[str, object] = {"n": n, **kwargs}
        try:
            return translated.format_map(all_kwargs)
        except (KeyError, IndexError, ValueError):
            source = singular if n == 1 else plural
            try:
                return source.format_map(all_kwargs)
            except (KeyError, IndexError, ValueError):
                return source


def _pick_locale(preferred: Sequence[str]) -> tuple[str, str | None]:
    """Pick (lang, region) for the first supported preferred locale.

    Languages are matched in preferred order against SUPPORTED_LANG; an
    unrecognized set falls back to ("en", None). The region is the 2-letter
    subtag of the matched locale, if any.
    """
    for tag in preferred:
        subtags = tag.replace("_", "-").split("-")
        lang = subtags[0].lower()
        if lang in SUPPORTED_LANG:
            for sub in subtags[1:]:
                if len(sub) == 2 and sub.isalpha():
                    return lang, sub.upper()
            return lang, None
    return "en", None


def _get_region_units(region: str | None) -> str:
    """Default units for a region: imperial for US, else metric."""
    return "imperial" if region in ("US",) else "metric"

def system_units() -> str | None:
    """OS preferred measurement system.

    Returns "metric" or "imperial" when the platform exposes a usable hint, else
    None so callers fall back to the locale region. Windows reads
    GetLocaleInfoEx(LOCALE_IMEASURE); macOS reads the AppleMeasurementUnits
    global user default; other platforms give no portable signal and return
    None.
    """
    if sys.platform == "win32":
        # Read LOCALE_IMEASURE for the current user (0 metric, 1 US)
        import ctypes
        from ctypes import wintypes

        LOCALE_IMEASURE = 0x0000000D
        LOCALE_RETURN_NUMBER = 0x20000000
        try:
            GetLocaleInfoEx = ctypes.windll.kernel32.GetLocaleInfoEx
            GetLocaleInfoEx.argtypes = [
                wintypes.LPCWSTR,
                wintypes.DWORD,
                wintypes.LPWSTR,
                ctypes.c_int,
            ]
            GetLocaleInfoEx.restype = ctypes.c_int
            value = wintypes.DWORD()
            chars = ctypes.sizeof(value) // ctypes.sizeof(ctypes.c_wchar)
            written = GetLocaleInfoEx(
                None,
                LOCALE_IMEASURE | LOCALE_RETURN_NUMBER,
                ctypes.cast(ctypes.pointer(value), wintypes.LPWSTR),
                chars
            )
        except OSError:
            return None
        if not written:
            return None
        return "imperial" if value.value == 1 else "metric"
    if sys.platform == "darwin":
        # AppleMeasurementUnits is "Inches" (imperial) or "Centimeters"
        import subprocess

        try:
            out = subprocess.run(
                ["defaults", "read", "-g", "AppleMeasurementUnits"],
                capture_output=True,
                text=True,
                timeout=2,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if out.returncode != 0:
            return None
        match out.stdout.strip().lower():
            case "inches":
                return "imperial"
            case "centimeters":
                return "metric"
            case _:
                return None
    return None


def system_locales() -> list[str]:
    """OS preferred locales as tags, most preferred first.

    Returns an empty list when the platform gives no usable hint, so callers
    fall back to English negotiation. Windows reads the user's preferred UI
    languages via GetUserPreferredUILanguages; macOS reads the AppleLocale
    global default; other platforms read the standard gettext environment
    variables (LANGUAGE holds a colon-separated priority list; LC_ALL,
    LC_MESSAGES and LANG each name a single locale).
    """
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        MUI_LANGUAGE_NAME = 0x8
        try:
            func = ctypes.windll.kernel32.GetUserPreferredUILanguages
            func.argtypes = [
                wintypes.DWORD,
                ctypes.POINTER(wintypes.ULONG),
                wintypes.LPWSTR,
                ctypes.POINTER(wintypes.ULONG),
            ]
            func.restype = wintypes.BOOL
            count = wintypes.ULONG()
            size = wintypes.ULONG()
            if not func(
                MUI_LANGUAGE_NAME, ctypes.byref(count), None,
                ctypes.byref(size)
            ):
                return []
            buf = ctypes.create_unicode_buffer(size.value)
            if not func(
                MUI_LANGUAGE_NAME, ctypes.byref(count), buf,
                ctypes.byref(size)
            ):
                return []
        except OSError:
            return []
        raw = "".join(buf[:size.value])
        return [tag for tag in raw.split("\x00") if tag]

    if sys.platform == "darwin":
        import subprocess

        try:
            out = subprocess.run(
                ["defaults", "read", "-g", "AppleLocale"],
                capture_output=True,
                text=True,
                timeout=2,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        if out.returncode != 0:
            return []
        tag = out.stdout.strip()
        return [tag] if tag else []

    import os

    language = os.environ.get("LANGUAGE")
    if language:
        tags = [_clean_locale(v) for v in language.split(":") if v]
        if tags:
            return tags
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value and value not in ("C", "POSIX"):
            return [_clean_locale(value)]
    return []


def _clean_locale(value: str) -> str:
    """Drop the ``.encoding`` and ``@modifier`` suffixes from a locale."""
    return value.split(".")[0].split("@")[0]


i18n = I18n()
"""Process-wide translator, shared by every module that renders text."""
