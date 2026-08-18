#!/bin/sh
# Build the app. Without arguments it compiles the frontend assets and the
# message catalogs. Pass --app to also produce the distributable package, and
# --debug for a console (non windowed) distributable. Python and its tools
# (pybabel, PyInstaller) come from PATH; activate a virtual environment first
# if you want to build against one.
set -eu

ROOT="$(cd "$(dirname "$0")" && pwd)"

PYTHON=python
PATH="$ROOT/bin/node_modules/.bin:$PATH"
export PATH
export NODE_PATH="$ROOT/bin/node_modules"

run() {
  echo "+ $*"
  "$@"
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
  "$ROOT/src/backpack/__main__.py"

if [ "$OS" = macos ] && [ "$WINDOW" = --windowed ]; then
  ver="$("$PYTHON" -c \
    "from importlib.metadata import version; print(version('backpack'))")"
  run ditto -c -k --sequesterRsrc --keepParent \
    "$OUTDIR/dist/backpack.app" \
    "$OUTDIR/backpack-$ver-$OSARCH.zip"
else
  run "$PYTHON" "$ROOT/scripts/mkzip.py" "$OUTDIR/dist" "$OSARCH"
fi
