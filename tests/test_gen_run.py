"""Tests for scripts/gen_run.py - the release launcher generator.

The script lives outside the package, so its directory is put on sys.path
before import. Real templates under scripts/ are used for the end to end
generate and main tests, while the unit tests build small fixtures on disk.
"""
import hashlib
import re
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import gen_run

PLACEHOLDER_RE = re.compile(r"@[A-Z][A-Z0-9_]*@")


def make_zip(
    zips: Path, version: str, os_name: str, arch: str, data: bytes = b"z"
) -> Path:
    """Write a fake release zip and return its path."""
    zips.mkdir(parents=True, exist_ok=True)
    path = zips / f"backpack-{version}-{os_name}-{arch}.zip"
    path.write_bytes(data)
    return path


class TestSha256File:
    def test_matches_hashlib(self, tmp_path: Path) -> None:
        data = b"backpack release bytes"
        path = tmp_path / "asset.zip"
        path.write_bytes(data)
        assert gen_run.sha256_file(path) == hashlib.sha256(data).hexdigest()

    def test_empty_file(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.zip"
        path.write_bytes(b"")
        assert gen_run.sha256_file(path) == hashlib.sha256(b"").hexdigest()


class TestCollectAssets:
    def test_single_asset(self, tmp_path: Path) -> None:
        zip_path = make_zip(tmp_path, "0.1.0", "macos", "arm64", b"mac")
        assets = gen_run.collect_assets(tmp_path)
        assert set(assets) == {"macos-arm64"}
        name, sha = assets["macos-arm64"]
        assert name == "backpack-0.1.0-macos-arm64.zip"
        assert sha == gen_run.sha256_file(zip_path)

    def test_multiple_arches_same_version(self, tmp_path: Path) -> None:
        make_zip(tmp_path, "0.1.0", "macos", "arm64")
        make_zip(tmp_path, "0.1.0", "windows", "x64")
        assets = gen_run.collect_assets(tmp_path)
        assert set(assets) == {"macos-arm64", "windows-x64"}

    def test_no_zips_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="no zip files"):
            gen_run.collect_assets(tmp_path)

    def test_unexpected_name_raises(self, tmp_path: Path) -> None:
        (tmp_path / "backpack-nightly.zip").write_bytes(b"x")
        with pytest.raises(ValueError, match="unexpected asset name"):
            gen_run.collect_assets(tmp_path)

    def test_duplicate_os_arch_raises(self, tmp_path: Path) -> None:
        """Two versions of the same os-arch collide on one key."""
        make_zip(tmp_path, "0.1.0", "macos", "arm64")
        make_zip(tmp_path, "0.2.0", "macos", "arm64")
        with pytest.raises(ValueError, match="duplicate asset"):
            gen_run.collect_assets(tmp_path)

    def test_mixed_versions_raises(self, tmp_path: Path) -> None:
        make_zip(tmp_path, "0.1.0", "macos", "arm64")
        make_zip(tmp_path, "0.2.0", "windows", "x64")
        with pytest.raises(ValueError, match="mixed versions"):
            gen_run.collect_assets(tmp_path)


class TestSubstitutions:
    def _assets(self) -> dict[str, tuple[str, str]]:
        return {
            "macos-arm64": ("backpack-0.1.0-macos-arm64.zip", "aa"),
        }

    def test_core_values(self) -> None:
        values = gen_run.substitutions(self._assets(), "v0.1.0", "o/r")
        assert values["TAG"] == "v0.1.0"
        assert values["VERSION"] == "0.1.0"
        assert values["REPO"] == "o/r"

    def test_present_key_tokens(self) -> None:
        values = gen_run.substitutions(self._assets(), "v0.1.0", "o/r")
        assert values["ASSET_MACOS_ARM64"] == (
            "backpack-0.1.0-macos-arm64.zip"
        )
        assert values["SHA_MACOS_ARM64"] == "aa"
        assert values["URL_MACOS_ARM64"] == (
            "https://github.com/o/r/releases/download/v0.1.0/"
            "backpack-0.1.0-macos-arm64.zip"
        )

    def test_absent_key_is_empty(self) -> None:
        values = gen_run.substitutions(self._assets(), "v0.1.0", "o/r")
        assert values["ASSET_WINDOWS_X64"] == ""
        assert values["SHA_WINDOWS_X64"] == ""
        assert values["URL_WINDOWS_X64"] == ""

    def test_tag_without_v_prefix(self) -> None:
        values = gen_run.substitutions(self._assets(), "0.1.0", "o/r")
        assert values["TAG"] == "0.1.0"
        assert values["VERSION"] == "0.1.0"

    def test_version_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="does not match"):
            gen_run.substitutions(self._assets(), "v0.2.0", "o/r")


class TestFill:
    def test_replaces_placeholders(self) -> None:
        out = gen_run.fill(
            "tag=@TAG@ ver=@VERSION@",
            {"TAG": "v0.1.0", "VERSION": "0.1.0"},
        )
        assert out == "tag=v0.1.0 ver=0.1.0"

    def test_empty_value_clears_placeholder(self) -> None:
        out = gen_run.fill("url=@URL_WINDOWS_X64@", {"URL_WINDOWS_X64": ""})
        assert out == "url="

    def test_leftover_placeholder_raises(self) -> None:
        with pytest.raises(ValueError, match="unsubstituted placeholders"):
            gen_run.fill("tag=@TAG@ missing=@MISSING@", {"TAG": "v0.1.0"})


class TestGenerate:
    def test_writes_both_launchers(self, tmp_path: Path) -> None:
        zips = tmp_path / "zips"
        out = tmp_path / "out"
        make_zip(zips, "0.1.0", "macos", "arm64", b"mac")
        make_zip(zips, "0.1.0", "windows", "x64", b"win")

        gen_run.generate(zips, "v0.1.0", "o/r", out, SCRIPTS_DIR)

        sh = (out / "run.sh").read_text(encoding="utf-8")
        ps1 = (out / "run.ps1").read_text(encoding="utf-8")
        assert "TAG=v0.1.0" in sh
        assert "VERSION=0.1.0" in sh
        assert (
            "https://github.com/o/r/releases/download/v0.1.0/"
            "backpack-0.1.0-macos-arm64.zip"
        ) in sh
        assert "$Tag = 'v0.1.0'" in ps1
        assert (
            "https://github.com/o/r/releases/download/v0.1.0/"
            "backpack-0.1.0-windows-x64.zip"
        ) in ps1

    def test_no_placeholders_left(self, tmp_path: Path) -> None:
        zips = tmp_path / "zips"
        out = tmp_path / "out"
        make_zip(zips, "0.1.0", "macos", "arm64")
        make_zip(zips, "0.1.0", "windows", "x64")

        gen_run.generate(zips, "v0.1.0", "o/r", out, SCRIPTS_DIR)

        for name in ("run.sh", "run.ps1"):
            text = (out / name).read_text(encoding="utf-8")
            assert PLACEHOLDER_RE.search(text) is None

    def test_lf_line_endings(self, tmp_path: Path) -> None:
        zips = tmp_path / "zips"
        out = tmp_path / "out"
        make_zip(zips, "0.1.0", "macos", "arm64")
        make_zip(zips, "0.1.0", "windows", "x64")

        gen_run.generate(zips, "v0.1.0", "o/r", out, SCRIPTS_DIR)

        for name in ("run.sh", "run.ps1"):
            raw = (out / name).read_bytes()
            assert b"\r\n" not in raw
            assert b"\n" in raw

    def test_creates_missing_outdir(self, tmp_path: Path) -> None:
        zips = tmp_path / "zips"
        out = tmp_path / "nested" / "out"
        make_zip(zips, "0.1.0", "macos", "arm64")
        make_zip(zips, "0.1.0", "windows", "x64")

        gen_run.generate(zips, "v0.1.0", "o/r", out, SCRIPTS_DIR)

        assert out.is_dir()

    def test_missing_windows_zip_raises(self, tmp_path: Path) -> None:
        zips = tmp_path / "zips"
        out = tmp_path / "out"
        make_zip(zips, "0.1.0", "macos", "arm64")

        with pytest.raises(ValueError, match="no windows zip"):
            gen_run.generate(zips, "v0.1.0", "o/r", out, SCRIPTS_DIR)

    def test_missing_macos_zip_raises(self, tmp_path: Path) -> None:
        zips = tmp_path / "zips"
        out = tmp_path / "out"
        make_zip(zips, "0.1.0", "windows", "x64")

        with pytest.raises(ValueError, match="no macos zip"):
            gen_run.generate(zips, "v0.1.0", "o/r", out, SCRIPTS_DIR)
        assert not (out / "run.sh").exists()


class TestMain:
    def test_wrong_arg_count_returns_2(self) -> None:
        assert gen_run.main(["zips", "v0.1.0", "o/r"]) == 2

    def test_success_writes_launchers(self, tmp_path: Path) -> None:
        zips = tmp_path / "zips"
        out = tmp_path / "out"
        make_zip(zips, "0.1.0", "macos", "arm64")
        make_zip(zips, "0.1.0", "windows", "x64")

        rc = gen_run.main([str(zips), "v0.1.0", "o/r", str(out)])

        assert rc == 0
        assert (out / "run.sh").is_file()
        assert (out / "run.ps1").is_file()
