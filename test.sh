#!/bin/sh
# Run the test suites. With no arguments it runs every suite. Pass one or more
# suite names (pytest, vitest) to run just those, in order.
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
OUTDIR="$ROOT/bin/$OS-$ARCH"
mkdir -p "$OUTDIR"

# Each suite is a run_<name> function. Routing is a name lookup, so a
# new suite is just a new function plus its name in ALL.
ALL="pytest vitest"

run_pytest() {
  run "$PYTHON" -m pytest --junitxml="$OUTDIR/pytest-report.xml"
}

run_vitest() {
  mkdir -p "$ROOT/bin"
  cp "$ROOT/src/ui/package.json" "$ROOT/bin/package.json"
  cp "$ROOT/src/ui/package-lock.json" "$ROOT/bin/package-lock.json"
  run npm --prefix "$ROOT/bin" install
  run npm --prefix "$ROOT/bin" exec -- vitest run \
    --config "$ROOT/src/ui/vite.config.ts" \
    --reporter=default --reporter=junit \
    --outputFile.junit="$OUTDIR/vitest-report.xml"
}

[ "$#" -gt 0 ] || set -- $ALL

for name in "$@"; do
  command -v "run_$name" >/dev/null 2>&1 || {
    echo "Unknown argument: $name" >&2
    exit 2
  }
done

for name in "$@"; do
  "run_$name"
done
