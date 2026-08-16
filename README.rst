Backpacking trip planner
========================

Setup
-----

From the repository root, create the virtual environment and install the package
with its dev extras::

    python -m venv .venv
    .venv\Scripts\python.exe -m pip install --editable ".[dev]"

Build the frontend once so the app has assets to load. Node packages and
the compiled UI land under ``bin/``::

    make assets

Development
-----------

Use two terminals. The first serves the frontend with hot reload::

    npm --prefix bin exec -- vite --config ui/vite.config.ts

The second runs the app pointed at that dev server, so edits refresh
without a rebuild::

    .venv\Scripts\python.exe -m backpack --dev

Without ``--dev`` the app loads the built ``bin/assets/index.html``, so
run ``make assets`` after frontend changes when testing that path.

Checks
------

From the root, ``pytest`` type checks the Python sources through pytest-mypy,
one item per file::

    .venv\Scripts\python.exe -m pytest

TypeScript is checked separately::

    npm --prefix bin exec -- tsc --noEmit -p ui

Tests
-----

From the root, ``pytest`` runs the Python test suite (the same command also
type checks the sources through pytest-mypy)::

    .venv\Scripts\python.exe -m pytest

Vitest runs the frontend tests once::

    make vitest

Use this to re-run them as files change::

    npm --prefix bin exec -- vitest --config ui/vite.config.ts

Translations
------------

User facing Python strings are wrapped in ``i18n.gettext`` (or ``ngettext`` for
plurals), extracted with Babel into gettext catalogs under ``locales/``, and
negotiated at runtime against the OS locale. English is the source language and
the message id, so a missing catalog or entry falls back to the English text and
the app runs without any compiled catalog. Supported languages are listed in
``SUPPORTED_LANG`` in ``src/backpack/i18n.py``; the frontend keeps its own
catalogs under ``ui/locales/``.

Each language owns a catalog at ``locales/<lang>/LC_MESSAGES/backpack.po``.
The extraction config lives in ``babel.cfg`` and all commands run from the
repository root.

After changing or adding wrapped strings, refresh the template and merge the new
messages into every existing catalog::

    pybabel extract -F babel.cfg -o locales/backpack.pot .
    pybabel update -i locales/backpack.pot -d locales -D backpack

``update`` marks changed entries ``fuzzy``; edit the ``msgstr`` values in each
``.po`` and drop the ``fuzzy`` flag once a translation is confirmed.

To add a new backend language, extend ``SUPPORTED_LANG`` in
``src/backpack/i18n.py``, create its catalog from the template, then fill in the
translations (``ru`` shown here)::

    pybabel init -i locales/backpack.pot -d locales -D backpack -l ru

Compile every catalog to the binary ``.mo`` files the app loads. Run this after
any ``.po`` edit and before packaging (``make locales`` wraps it)::

    pybabel compile -d locales -D backpack

Commit the ``.pot`` and ``.po`` sources; the generated ``.mo`` files are build
artifacts.

The frontend keeps its own catalogs as plain JSON under ``ui/locales/``, one
file per language (``en.json``, ``ru.json``), loaded by i18next in
``ui/i18n.ts``. There is no extraction step: keys are added by hand as strings
are wrapped in ``t("...")``, with English as the source and fallback, so a
missing key renders its English text. After editing a wrapped string, mirror the
key in every ``ui/locales/*.json`` file.

To add the same language on the frontend, copy ``ui/locales/en.json`` to
``ui/locales/<lang>.json``, translate its values, then register the language in
``ui/i18n.ts`` by adding it to ``supported_languages`` and importing it into the
i18next ``resources`` map. Both sides negotiate against the same tag, so add a
language to the backend ``SUPPORTED_LANG`` and the frontend
``supported_languages`` together.

Building
--------

All build tasks are driven by the top-level ``Makefile``. On Windows you need
GNU Make (the CI installs GnuWin32). Common targets::

    make assets    # compile frontend into bin/assets
    make locales   # compile catalogs into bin/locales
    make test      # run pytest + vitest (reports in bin/{os}-{arch}/)
    make pytest    # python tests only
    make vitest    # UI tests only
    make dist      # full package (assets + locales + PyInstaller + zip)
    make clean     # remove bin/ and caches
    make devenv    # rebuild assets and refresh the venv

Artifacts are placed under ``bin/{os}-{arch}/`` where ``{os}`` is ``windows``,
``linux``, or ``macos`` and ``{arch}`` is ``x64`` or ``arm64``. Node modules are
shared at ``bin/node_modules/``.

Running a release
-----------------

Each GitHub release includes a generated launcher with that tag's version, zip
URL, and SHA256 hardcoded. Fetching it with curl also skips macOS quarantine
and Windows SmartScreen, which hit a browser-downloaded unsigned zip.

macOS, latest::

    curl -fsSL https://github.com/stamerlan/backpack/releases/latest/download/run.sh | sh

Windows 11, latest (use ``curl.exe``, not ``curl``)::

    curl.exe -fsSL https://github.com/stamerlan/backpack/releases/latest/download/run.ps1 | powershell -NoProfile -ExecutionPolicy Bypass -Command -

A specific tag is the same file on that release. macOS::

    curl -fsSL https://github.com/stamerlan/backpack/releases/download/v0.1.0/run.sh | sh

The launcher unpacks to a temp directory, runs the app, and deletes the temp
files when the app exits. No extra tools are needed. Windows ARM uses a
``windows-arm64`` zip when that release has one, otherwise the ``windows-x64``
zip.

Packaging
---------

Standalone packages are built with PyInstaller (installed with the ``dev``
extras above), which cannot cross-compile, so build on the target OS::

    make dist

The result lands in ``bin/{os}-{arch}/dist/``: a ``backpack`` folder
holding ``backpack.exe`` and an ``app`` support folder on Windows, or
a ``backpack.app`` bundle on macOS, next to a versioned ``.zip``
archive. Pass ``WINDOW=--console`` to keep a console window for
debugging (``make dist WINDOW=--console``).

Remove all build output and caches with::

    make clean
