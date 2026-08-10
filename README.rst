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
