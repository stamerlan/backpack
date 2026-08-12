Backpacking trip planner
========================

Setup
-----

From the repository root, create the virtual environment and install the package
with its dev extras::

    python -m venv .venv
    .venv\Scripts\python.exe -m pip install --editable ".[dev]"

From ``ui/``, install the frontend packages and build them once so the app has
assets to load::

    cd ui
    npm install
    npm run build

Development
-----------

Use two terminals. The first, in ``ui/``, serves the frontend with hot reload::

    cd ui
    npm run dev

The second, in the repository root, runs the app pointed at that dev server, so
edits refresh without a rebuild::

    .venv\Scripts\python.exe -m backpack --dev

Without ``--dev`` the app loads the built ``assets/index.html``, so run
``npm run build`` in ``ui/`` after frontend changes when testing that path.

Checks
------

From the root, ``pytest`` type checks the Python sources through pytest-mypy,
one item per file::

    .venv\Scripts\python.exe -m pytest

From ``ui/``, TypeScript is checked separately::

    cd ui
    npm run check

Tests
-----

From the root, ``pytest`` runs the Python test suite (the same command also
type checks the sources through pytest-mypy)::

    .venv\Scripts\python.exe -m pytest

From ``ui/``, Vitest runs the frontend tests once::

    cd ui
    npm test

Use ``npm run test:watch`` from ``ui/`` to re-run them as files change.

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

Packaging
---------

Standalone packages are built with PyInstaller, which cannot cross compile, so
build on the target OS. Install the packaging tools once::

    .venv\Scripts\python.exe -m pip install --editable ".[pkg]"

Then build the frontend and the package in one step::

    .venv\Scripts\python.exe scripts\build.py

The result lands in ``dist/``: a ``backpack`` folder with
``backpack.exe`` on Windows and a ``backpack.app`` bundle on macOS. Pass
``--onefile`` for a single executable, ``--archive`` to zip a versioned
copy, ``--console`` to keep a console window for debugging, and
``--skip-frontend`` to reuse an existing ``assets/`` build.

Remove the build output and caches with::

    .venv\Scripts\python.exe scripts\clean.py

macOS Gatekeeper
----------------

The macOS package is not signed with an Apple Developer ID or notarized, so a
downloaded ``backpack.app`` is quarantined and macOS refuses to open it with a
"damaged and can't be opened" message. Clear the quarantine flag once, then open
it normally::

    xattr -dr com.apple.quarantine /path/to/backpack.app
    open /path/to/backpack.app
