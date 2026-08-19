#!/bin/sh
# Build the app. Without arguments it compiles the frontend assets and the
# message catalogs. Pass --app to also produce the distributable package, and
# --debug for a console (non windowed) distributable. The build creates and
# uses its own venv under bin/<os>-<arch>/.venv, installing the package with
# its tools.
set -eu

ROOT="$(cd "$(dirname "$0")" && pwd)"

PATH="$ROOT/bin/node_modules/.bin:$PATH"
export PATH
export NODE_PATH="$ROOT/bin/node_modules"

run() {
  echo "+ $*"
  "$@"
}

# Ensure the build venv exists with the package installed. A valid venv is
# reused for fast rebuilds.
ensure_venv() {
  if [ -x "$PYTHON" ] && "$PYTHON" -c pass >/dev/null 2>&1; then
    return 0
  fi
  rm -rf "$VENV"
  run python -m venv "$VENV"
  run "$PYTHON" -m pip install --upgrade pip
  run "$PYTHON" -m pip install --editable "$ROOT[dev]"
}

APP=0
WINDOW=--windowed
for arg in "$@"; do
  case "$arg" in
    --app) APP=1 ;;
    --debug) WINDOW=--console ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

case "$(uname -s)" in
  Darwin) OS=macos ;;
  Linux) OS=linux ;;
  *) OS="$(uname -s)" ;;
esac
case "$(uname -m)" in
  x86_64) ARCH=x64 ;;
  arm64 | aarch64) ARCH=arm64 ;;
  *) ARCH="$(uname -m)" ;;
esac
OSARCH="$OS-$ARCH"
OUTDIR="$ROOT/bin/$OSARCH"

# Build owned venv under the arch output dir, holding the package and its tools
# (pybabel, PyInstaller). clean.sh wipes it with the rest of bin/. A personal
# venv (e.g. at the repo root) is only for development.
VENV="$OUTDIR/.venv"
PYTHON="$VENV/bin/python"
ensure_venv
PATH="$VENV/bin:$PATH"
export PATH

if [ "$OS" = macos ]; then
  ICON="$ROOT/src/ui/public/icons/app.icns"
else
  ICON="$ROOT/src/ui/public/icons/app.png"
fi

# Frontend assets into bin/assets
mkdir -p "$ROOT/bin"
cp "$ROOT/src/ui/package.json" "$ROOT/bin/package.json"
cp "$ROOT/src/ui/package-lock.json" "$ROOT/bin/package-lock.json"
run npm --prefix "$ROOT/bin" install
run npm --prefix "$ROOT/bin" exec -- tsc --noEmit -p "$ROOT/src/ui"
run npm --prefix "$ROOT/bin" exec -- vite build \
  --config "$ROOT/src/ui/vite.config.ts"

# Message catalogs into bin/locales
rm -rf "$ROOT/bin/locales"
cp -r "$ROOT/locales" "$ROOT/bin/locales"
run pybabel compile -d "$ROOT/bin/locales" -D backpack

if [ "$APP" != 1 ]; then
  exit 0
fi

# Standalone PyInstaller distributable + zip
run "$PYTHON" -m PyInstaller --noconfirm --clean --onedir \
  --contents-directory app --name backpack \
  --distpath "$OUTDIR/dist" --workpath "$OUTDIR/build" \
  --specpath "$OUTDIR/build" --paths "$ROOT/src" \
  --add-data "$ROOT/bin/assets:assets" \
  --add-data "$ROOT/bin/locales:locales" \
  --collect-all webview \
  --recursive-copy-metadata pydantic-ai-slim \
  --exclude-module setuptools \
  --exclude-module pkg_resources \
  --exclude-module pip \
  --icon "$ICON" "$WINDOW" \
  "$ROOT/src/core/__main__.py"

if [ "$OS" = macos ] && [ "$WINDOW" = --windowed ]; then
  ver="$("$PYTHON" -c \
    "from importlib.metadata import version; print(version('backpack'))")"
  run ditto -c -k --sequesterRsrc --keepParent \
    "$OUTDIR/dist/backpack.app" \
    "$OUTDIR/backpack-$ver-$OSARCH.zip"
else
  run "$PYTHON" "$ROOT/scripts/mkzip.py" "$OUTDIR/dist" "$OSARCH"
fi
