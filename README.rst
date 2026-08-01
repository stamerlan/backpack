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
