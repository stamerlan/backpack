MAKEFILE_PATH := $(abspath $(lastword $(MAKEFILE_LIST)))
MAKEFILE_DIR := $(patsubst %/,%,$(dir $(MAKEFILE_PATH)))

PYTHON := python

.PHONY: all
all: assets

.PHONY: assets
assets:
	npm --prefix $(MAKEFILE_DIR)/ui install
	npm --prefix $(MAKEFILE_DIR)/ui run build

.PHONY: test
test: pytest vitest

.PHONY: pytest
pytest:
	$(PYTHON) -m pytest $(EXTRA_PYTEST_ARGS)

.PHONY: vitest
vitest:
	npm --prefix $(MAKEFILE_DIR)/ui run test -- $(EXTRA_VITEST_ARGS)

.PHONY: devenv
devenv: assets
	$(PYTHON) $(MAKEFILE_DIR)/scripts/venv.py


.PHONY: dist
dist: assets
	$(PYTHON) $(MAKEFILE_DIR)/scripts/dist.py $(EXTRA_DIST_ARGS)

.PHONY: clean
clean:
	$(PYTHON) $(MAKEFILE_DIR)/scripts/clean.py
