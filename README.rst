Backpacking trip planner
========================

Setup
-----

The build owns its Python environment: ``build`` creates a virtual environment
under ``bin/{os}-{arch}/.venv`` and installs the package with its tools into it,
so no preinstalled environment isneeded. A valid venv is reused, so repeat
builds and test runs stay fast; it is wiped by ``clean`` with the rest of
``bin/``. If you want an environment for editing or running the app by hand,
create your own (e.g. ``.venv`` at the repo root); the build never touches it.

Build the frontend and message catalogs once so the app has assets to load. Node
packages and the compiled UI land under ``bin/``. On Windows this also builds
the native app, which requires ``msvc``::

    build.bat        # Windows
    sh build.sh      # macOS

Development
-----------

Use two terminals. The first serves the frontend with hot reload::

    dev.bat

The second runs the app pointed at that dev server, so edits refresh without a
rebuild (use the build venv after a first ``build.bat``, or your own)::

    bin\windows-x64\.venv\Scripts\python.exe -m backpack --dev

Without ``--dev`` the app loads the built ``bin/assets/index.html``, so run
``build.bat`` after frontend changes when testing that path.

Checks
------

From the root, ``pytest`` type checks the Python sources through pytest-mypy,
one item per file::

    test.bat pytest        # Windows
    sh test.sh pytest      # macOS

TypeScript is checked separately::

    npm --prefix bin exec -- tsc --noEmit -p src/ui

Tests
-----

From the root, ``pytest`` runs the Python test suite (the same command also
type checks the sources through pytest-mypy)::

    test.bat pytest        # Windows
    sh test.sh pytest      # macOS

Vitest runs the frontend tests once::

    test.bat vitest        # Windows
    sh test.sh vitest      # macOS

Run both suites together with ``test.bat`` / ``sh test.sh`` (no
argument). Use this to re-run the frontend tests as files change::

    npm --prefix bin exec -- vitest --config src/ui/vite.config.ts

Translations
------------

User facing Python strings are wrapped in ``i18n.gettext`` (or ``ngettext`` for
plurals), extracted with Babel into gettext catalogs under ``locales/``, and
negotiated at runtime against the OS locale. English is the source language and
the message id, so a missing catalog or entry falls back to the English text and
the app runs without any compiled catalog. Supported languages are listed in
``SUPPORTED_LANG`` in ``src/backpack/i18n.py``; the frontend keeps its own
catalogs under ``src/ui/locales/``.

Each language owns a catalog at ``locales/<lang>/LC_MESSAGES/backpack.po``.
The extraction config lives in ``babel.cfg`` and all commands run from the
repository root. ``pybabel`` lives in the build venv
(``bin/{os}-{arch}/.venv``); run it from there or from your own venv.

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
any ``.po`` edit and before packaging (the build scripts wrap it)::

    pybabel compile -d locales -D backpack

Commit the ``.pot`` and ``.po`` sources; the generated ``.mo`` files are build
artifacts.

The frontend keeps its own catalogs as plain JSON under ``src/ui/locales/``, one
file per language (``en.json``, ``ru.json``), loaded by i18next in
``src/ui/i18n.ts``. There is no extraction step: keys are added by hand as strings
are wrapped in ``t("...")``, with English as the source and fallback, so a
missing key renders its English text. After editing a wrapped string, mirror the
key in every ``src/ui/locales/*.json`` file.

To add the same language on the frontend, copy ``src/ui/locales/en.json`` to
``src/ui/locales/<lang>.json``, translate its values, then register the language in
``src/ui/i18n.ts`` by adding it to ``supported_languages`` and importing it into the
i18next ``resources`` map. Both sides negotiate against the same tag, so add a
language to the backend ``SUPPORTED_LANG`` and the frontend
``supported_languages`` together.

Building
--------

Build tasks are driven by small per OS scripts at the repository root:
``.bat`` on Windows and ``.sh`` on macOS. Common commands (Windows form
shown; use ``sh <name>.sh`` on macOS)::

    build.bat          # frontend assets + catalogs + native host
    build.bat --debug  # same, native host built in Debug
    build.bat --app    # also build the PyInstaller distributable + zip
    test.bat           # run pytest + vitest (reports in bin/{os}-{arch}/)
    test.bat pytest    # python tests only
    test.bat vitest    # UI tests only
    dev.bat            # serve the frontend with hot reload (Windows only)

The native ``backpack.exe`` host is Windows only and requires ``msvc`` (run from
a Visual Studio developer prompt, or install the VS Build Tools). On macOS
``build.sh`` builds the frontend assets and catalogs, and ``--app`` produces the
distributable.

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

The launcher caches the downloaded zip and unpacked app under a per user cache
directory, keyed by the release SHA256. A later run reuses the cached image when
the SHA still matches and only downloads again when it does not, so repeated
runs start without a fresh download. The cache lives at
``$XDG_CACHE_HOME/backpack`` (default ``~/.cache/backpack``) on macOS and
``%LOCALAPPDATA%\backpack\cache`` on Windows; set ``BACKPACK_CACHE`` to
override it.

Packaging
---------

Standalone packages are built with PyInstaller (installed with the ``dev``
extras above), which cannot cross-compile, so build on the target OS::

    build.bat --app        # Windows
    sh build.sh --app      # macOS

The build populates ``bin/{os}-{arch}/``. Under ``dist/`` you get the unpacked
app: a ``backpack`` folder holding ``backpack.exe`` and an ``app`` support
folder on Windows, or a ``backpack.app`` bundle on macOS. The versioned ``.zip``
archive is written directly to ``bin/{os}-{arch}/``. Pass ``--debug`` to keep a
console window for debugging (``build.bat --app --debug``).
