MAKEFILE_PATH := $(abspath $(lastword $(MAKEFILE_LIST)))
MAKEFILE_DIR := $(patsubst %/,%,$(dir $(MAKEFILE_PATH)))

include scripts/os.mk

PYTHON := python
NPM := npm
OUTDIR := bin/$(OSARCH)

VERSION := $(shell $(PYTHON) -c \
  "from importlib.metadata import version; print(version('backpack'))")
WINDOW ?= --windowed

export NODE_PATH := $(MAKEFILE_DIR)/bin/node_modules

.PHONY: all
all: assets locales

.PHONY: bin/node_modules
bin/node_modules: bin/package.json bin/package-lock.json
	$(NPM) --prefix bin install

bin/package.json: ui/package.json
	-$(call MKDIR,bin)
	$(call CP,ui/package.json,bin/package.json)

bin/package-lock.json: ui/package-lock.json
	-$(call MKDIR,bin)
	$(call CP,ui/package-lock.json,bin/package-lock.json)

.PHONY: assets
assets: bin/node_modules
	$(NPM) --prefix bin exec -- tsc --noEmit -p ui
	$(NPM) --prefix bin exec -- vite build --config ui/vite.config.ts

.PHONY: dev
dev: bin/node_modules
	$(NPM) --prefix bin exec -- vite --config ui/vite.config.ts

.PHONY: locales
locales:
	-$(call RMDIR,bin/locales)
	-$(call MKDIR,bin)
	$(call CPDIR,locales,bin/locales)
	pybabel compile -d bin/locales -D backpack

.PHONY: dist
dist: assets locales
	$(PYTHON) -m PyInstaller --noconfirm --clean --onedir \
	  --contents-directory app --name backpack \
	  --distpath "$(OUTDIR)/dist" --workpath "$(OUTDIR)/build" \
	  --specpath "$(OUTDIR)/build" --paths src \
	  --add-data "$(MAKEFILE_DIR)/bin/assets:assets" \
	  --add-data "$(MAKEFILE_DIR)/bin/locales:locales" \
	  --collect-all webview \
	  --recursive-copy-metadata pydantic-ai-slim \
	  --exclude-module setuptools \
	  --exclude-module pkg_resources \
	  --exclude-module pip \
	  --icon "$(MAKEFILE_DIR)/$(ICON)" $(WINDOW) \
	  src/backpack/__main__.py
ifeq ($(HOST_OS),macos)
	ditto -c -k --sequesterRsrc --keepParent "$(OUTDIR)/dist/backpack.app" \
	$(OUTDIR)/backpack-$(VERSION)-$(OSARCH).zip
else
	$(PYTHON) -c "import shutil; shutil.make_archive(\
	  '$(OUTDIR)/dist/backpack-$(VERSION)-$(OSARCH)',\
	  'zip', '$(OUTDIR)/dist', 'backpack')"
endif

.PHONY: test
test: pytest vitest

.PHONY: pytest
pytest:
	-$(call MKDIR,$(OUTDIR))
	$(PYTHON) -m pytest \
	  --junitxml="$(OUTDIR)/pytest-report.xml" \
	  $(EXTRA_PYTEST_ARGS)

.PHONY: vitest
vitest: bin/node_modules
	-$(call MKDIR,$(OUTDIR))
	$(NPM) --prefix bin exec -- vitest run \
	  --config ui/vite.config.ts \
	  --reporter=default --reporter=junit \
	  --outputFile.junit="$(MAKEFILE_DIR)/$(OUTDIR)/vitest-report.xml" \
	  $(EXTRA_VITEST_ARGS)

.PHONY: devenv
devenv: assets
	$(PYTHON) $(MAKEFILE_DIR)/scripts/venv.py

.PHONY: clean
clean:
	$(PYTHON) $(MAKEFILE_DIR)/scripts/clean.py
