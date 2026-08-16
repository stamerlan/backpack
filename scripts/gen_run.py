"""Fill run.sh / run.ps1 templates from release zip files."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ASSET_RE = re.compile(
    r"^backpack-(.+)-(macos|windows|linux)-(x64|arm64)\.zip$"
)
PLACEHOLDER_RE = re.compile(r"@[A-Z][A-Z0-9_]*@")
KEYS = (
    "macos-arm64",
    "macos-x64",
    "windows-x64",
    "windows-arm64",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def collect_assets(zips: Path) -> dict[str, tuple[str, str]]:
    assets: dict[str, tuple[str, str]] = {}
    versions: set[str] = set()
    found = sorted(zips.glob("backpack-*.zip"))
    if not found:
        raise ValueError(f"no zip files in {zips}")
    for path in found:
        m = ASSET_RE.match(path.name)
        if m is None:
            raise ValueError(f"unexpected asset name: {path.name!r}")
        version, os_name, arch = m.group(1, 2, 3)
        versions.add(version)
        key = f"{os_name}-{arch}"
        if key in assets:
            raise ValueError(f"duplicate asset: {path.name}")
        assets[key] = (path.name, sha256_file(path))
    if len(versions) != 1:
        raise ValueError(f"mixed versions in zips: {versions}")
    return assets


def substitutions(
    assets: dict[str, tuple[str, str]], tag: str, repo: str
) -> dict[str, str]:
    version = tag[1:] if tag.startswith("v") else tag
    file_ver = next(iter(assets.values()))[0]
    m = ASSET_RE.match(file_ver)
    assert m is not None
    if m.group(1) != version:
        raise ValueError(
            f"tag {tag} does not match zip version {m.group(1)}"
        )
    values = {
        "TAG": tag,
        "VERSION": version,
        "REPO": repo,
    }
    base = f"https://github.com/{repo}/releases/download/{tag}"
    for key in KEYS:
        token = key.replace("-", "_").upper()
        if key in assets:
            name, sha = assets[key]
            values[f"ASSET_{token}"] = name
            values[f"SHA_{token}"] = sha
            values[f"URL_{token}"] = f"{base}/{name}"
        else:
            values[f"ASSET_{token}"] = ""
            values[f"SHA_{token}"] = ""
            values[f"URL_{token}"] = ""
    return values


def fill(template: str, values: dict[str, str]) -> str:
    out = template
    for key, value in values.items():
        out = out.replace(f"@{key}@", value)
    leftover = PLACEHOLDER_RE.findall(out)
    if leftover:
        raise ValueError(f"unsubstituted placeholders: {leftover}")
    return out


def generate(
    zips: Path, tag: str, repo: str, outdir: Path, templates: Path
) -> None:
    assets = collect_assets(zips)
    values = substitutions(assets, tag, repo)
    outdir.mkdir(parents=True, exist_ok=True)
    mapping = (
        ("run.sh.in", "run.sh", "macos"),
        ("run.ps1.in", "run.ps1", "windows"),
    )
    for src_name, dst_name, os_name in mapping:
        if not any(k.startswith(os_name) for k in assets):
            raise ValueError(f"no {os_name} zip in {zips}")
        src = templates / src_name
        text = fill(src.read_text(encoding="utf-8"), values)
        dest = outdir / dst_name
        dest.write_text(text, encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 4:
        print("usage: gen_run.py ZIPS TAG REPO OUTDIR", file=sys.stderr)
        return 2
    zips, tag, repo, outdir = args
    generate(
        Path(zips), tag, repo, Path(outdir), Path(__file__).resolve().parent
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
