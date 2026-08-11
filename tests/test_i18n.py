"""Tests for backpack.i18n - gettext runtime."""
from gettext import NullTranslations
from pathlib import Path
from unittest.mock import patch

from backpack import APP_NAME
from backpack.i18n import (
    I18n,
    _get_region_units,
    _pick_locale,
    system_units,
)


class TestPickLocale:
    def test_exact_match(self) -> None:
        assert _pick_locale(["ru"]) == ("ru", None)

    def test_region_tag_hyphen(self) -> None:
        assert _pick_locale(["ru-RU"]) == ("ru", "RU")

    def test_region_tag_underscore(self) -> None:
        assert _pick_locale(["ru_RU"]) == ("ru", "RU")

    def test_unsupported_falls_back_to_en(self) -> None:
        assert _pick_locale(["fr"]) == ("en", None)

    def test_empty_list_falls_back_to_en(self) -> None:
        assert _pick_locale([]) == ("en", None)

    def test_first_supported_wins(self) -> None:
        assert _pick_locale(["fr", "ru", "en"]) == ("ru", None)

    def test_case_insensitive(self) -> None:
        assert _pick_locale(["RU"]) == ("ru", None)

    def test_en_is_supported(self) -> None:
        assert _pick_locale(["en"]) == ("en", None)

    def test_en_us(self) -> None:
        assert _pick_locale(["en-US"]) == ("en", "US")

    def test_region_from_matched_locale(self) -> None:
        """Region comes from the matched locale, not an earlier one."""
        assert _pick_locale(["fr-FR", "en-US"]) == ("en", "US")

    def test_skips_script_subtag(self) -> None:
        assert _pick_locale(["ru-Cyrl-RU"]) == ("ru", "RU")


class TestRegionUnits:
    def test_us_imperial(self) -> None:
        assert _get_region_units("US") == "imperial"

    def test_other_metric(self) -> None:
        assert _get_region_units("GB") == "metric"

    def test_none_metric(self) -> None:
        assert _get_region_units(None) == "metric"


class TestLoad:
    def test_missing_catalog_uses_english(
        self, tmp_path: Path
    ) -> None:
        """No .mo file - messages pass through as English."""
        i18n = I18n()
        with patch(
            "backpack.i18n.locales_dir",
            return_value=tmp_path,
        ):
            i18n.load("ru")
        assert i18n.lang == "ru"
        assert i18n.gettext("Hello") == "Hello"

    def test_unsupported_locale_negotiates_to_en(
        self, tmp_path: Path
    ) -> None:
        i18n = I18n()
        with patch(
            "backpack.i18n.locales_dir",
            return_value=tmp_path,
        ):
            i18n.load("fr")
        assert i18n.lang == "en"

    def test_load_string_arg(self, tmp_path: Path) -> None:
        """A single string is accepted (not just a list)."""
        i18n = I18n()
        with patch(
            "backpack.i18n.locales_dir",
            return_value=tmp_path,
        ):
            i18n.load("en")
        assert i18n.lang == "en"

    def test_load_sequence_arg(self, tmp_path: Path) -> None:
        i18n = I18n()
        with patch(
            "backpack.i18n.locales_dir",
            return_value=tmp_path,
        ):
            i18n.load(["fr", "ru"])
        assert i18n.lang == "ru"


class TestTag:
    def _load(self, tmp_path: Path, locale: str) -> I18n:
        i18n = I18n()
        with patch(
            "backpack.i18n.locales_dir",
            return_value=tmp_path,
        ):
            i18n.load(locale)
        return i18n

    def test_region_kept_in_tag(self, tmp_path: Path) -> None:
        assert self._load(tmp_path, "en-GB").tag == "en-GB"

    def test_regionless_tag_is_language(self, tmp_path: Path) -> None:
        assert self._load(tmp_path, "en").tag == "en"

    def test_ru_region(self, tmp_path: Path) -> None:
        assert self._load(tmp_path, "ru-RU").tag == "ru-RU"

    def test_unsupported_tag_falls_back_to_en(
        self, tmp_path: Path
    ) -> None:
        i18n = self._load(tmp_path, "fr-FR")
        assert i18n.tag == "en"
        assert i18n.lang == "en"

    def test_underscore_tag_normalized_to_hyphen(
        self, tmp_path: Path
    ) -> None:
        assert self._load(tmp_path, "en_US").tag == "en-US"

    def test_default_tag_is_en(self) -> None:
        assert I18n().tag == "en"


class TestDialectCatalog:
    def test_dialect_prefers_region_then_base(
        self, tmp_path: Path
    ) -> None:
        with patch(
            "backpack.i18n.locales_dir",
            return_value=tmp_path,
        ), patch(
            "backpack.i18n.Translations.load",
            return_value=NullTranslations(),
        ) as load:
            I18n().load("en-GB")
        assert load.call_args.args[1] == ["en_GB", "en"]

    def test_regionless_loads_base_only(
        self, tmp_path: Path
    ) -> None:
        with patch(
            "backpack.i18n.locales_dir",
            return_value=tmp_path,
        ), patch(
            "backpack.i18n.Translations.load",
            return_value=NullTranslations(),
        ) as load:
            I18n().load("ru")
        assert load.call_args.args[1] == ["ru"]


class TestGettext:
    def test_passthrough_no_kwargs(self) -> None:
        i18n = I18n()
        assert i18n.gettext("Hello") == "Hello"

    def test_format_kwargs(self) -> None:
        i18n = I18n()
        result = i18n.gettext(
            "Hello {name}", name="World"
        )
        assert result == "Hello World"

    def test_bad_placeholder_falls_back_to_source(
        self,
    ) -> None:
        i18n = I18n()
        result = i18n.gettext(
            "Hello {name}", wrong="arg"
        )
        assert result == "Hello {name}"

    def test_multiple_kwargs(self) -> None:
        i18n = I18n()
        result = i18n.gettext(
            "{a} and {b}", a="X", b="Y"
        )
        assert result == "X and Y"


class TestNgettext:
    def test_singular(self) -> None:
        i18n = I18n()
        result = i18n.ngettext(
            "{n} route", "{n} routes", 1
        )
        assert result == "1 route"

    def test_plural(self) -> None:
        i18n = I18n()
        result = i18n.ngettext(
            "{n} route", "{n} routes", 3
        )
        assert result == "3 routes"

    def test_zero_is_plural(self) -> None:
        i18n = I18n()
        result = i18n.ngettext(
            "{n} route", "{n} routes", 0
        )
        assert result == "0 routes"

    def test_extra_kwargs(self) -> None:
        i18n = I18n()
        result = i18n.ngettext(
            "{n} route in {name}",
            "{n} routes in {name}",
            2,
            name="Alps",
        )
        assert result == "2 routes in Alps"

    def test_bad_placeholder_falls_back_to_source(
        self,
    ) -> None:
        i18n = I18n()
        result = i18n.ngettext(
            "{n} route for {name}",
            "{n} routes for {name}",
            2,
            wrong="arg",
        )
        assert result == "{n} routes for {name}"

    def test_singular_bad_placeholder(self) -> None:
        i18n = I18n()
        result = i18n.ngettext(
            "{n} item for {x}",
            "{n} items for {x}",
            1,
            wrong="arg",
        )
        assert result == "{n} item for {x}"


class TestDomain:
    def test_load_uses_app_name_domain(
        self, tmp_path: Path
    ) -> None:
        i18n = I18n()
        with patch(
            "backpack.i18n.locales_dir",
            return_value=tmp_path,
        ), patch(
            "backpack.i18n.Translations.load",
            return_value=NullTranslations(),
        ) as load:
            i18n.load("en")
        assert load.call_args.args[2] == APP_NAME


class TestUnits:
    def test_system_preference_wins(
        self, tmp_path: Path
    ) -> None:
        """OS hint overrides the locale region default."""
        i18n = I18n()
        with patch(
            "backpack.i18n.locales_dir",
            return_value=tmp_path,
        ), patch(
            "backpack.i18n.system_units",
            return_value="imperial",
        ):
            i18n.load("ru-RU")
        assert i18n.units == "imperial"

    def test_falls_back_to_us_region(
        self, tmp_path: Path
    ) -> None:
        i18n = I18n()
        with patch(
            "backpack.i18n.locales_dir",
            return_value=tmp_path,
        ), patch(
            "backpack.i18n.system_units",
            return_value=None,
        ):
            i18n.load("en-US")
        assert i18n.units == "imperial"

    def test_falls_back_to_metric_non_us(
        self, tmp_path: Path
    ) -> None:
        i18n = I18n()
        with patch(
            "backpack.i18n.locales_dir",
            return_value=tmp_path,
        ), patch(
            "backpack.i18n.system_units",
            return_value=None,
        ):
            i18n.load("en-GB")
        assert i18n.units == "metric"

    def test_regionless_locale_defaults_metric(
        self, tmp_path: Path
    ) -> None:
        i18n = I18n()
        with patch(
            "backpack.i18n.locales_dir",
            return_value=tmp_path,
        ), patch(
            "backpack.i18n.system_units",
            return_value=None,
        ):
            i18n.load("ru")
        assert i18n.units == "metric"

    def test_en_underscore_us_imperial(
        self, tmp_path: Path
    ) -> None:
        i18n = I18n()
        with patch(
            "backpack.i18n.locales_dir",
            return_value=tmp_path,
        ), patch(
            "backpack.i18n.system_units",
            return_value=None,
        ):
            i18n.load("en_us")
        assert i18n.units == "imperial"

    def test_plain_en_metric(self, tmp_path: Path) -> None:
        i18n = I18n()
        with patch(
            "backpack.i18n.locales_dir",
            return_value=tmp_path,
        ), patch(
            "backpack.i18n.system_units",
            return_value=None,
        ):
            i18n.load("en")
        assert i18n.units == "metric"

    def test_default_units_before_load(self) -> None:
        assert I18n().units == "metric"


class TestSystemUnits:
    def _run(self, returncode: int, stdout: str) -> object:
        return type(
            "R", (), {"returncode": returncode, "stdout": stdout}
        )()

    def test_macos_inches_imperial(self) -> None:
        with patch("backpack.i18n.sys.platform", "darwin"), patch(
            "subprocess.run",
            return_value=self._run(0, "Inches\n"),
        ):
            assert system_units() == "imperial"

    def test_macos_centimeters_metric(self) -> None:
        with patch("backpack.i18n.sys.platform", "darwin"), patch(
            "subprocess.run",
            return_value=self._run(0, "Centimeters\n"),
        ):
            assert system_units() == "metric"

    def test_macos_unset_returns_none(self) -> None:
        """A missing default gives a nonzero exit - no hint."""
        with patch("backpack.i18n.sys.platform", "darwin"), patch(
            "subprocess.run",
            return_value=self._run(1, ""),
        ):
            assert system_units() is None

    def test_macos_missing_tool_returns_none(self) -> None:
        with patch("backpack.i18n.sys.platform", "darwin"), patch(
            "subprocess.run",
            side_effect=OSError,
        ):
            assert system_units() is None

    def test_unknown_platform_returns_none(self) -> None:
        with patch("backpack.i18n.sys.platform", "linux"):
            assert system_units() is None
