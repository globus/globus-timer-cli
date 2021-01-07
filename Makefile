VIRTUAL_ENV ?= .venv
LINT_PATHS=timer_cli/
ISORT_OPTS=--recursive \
	--multi-line 3 \
	--trailing-comma \
	--use-parentheses \
	--force-sort-within-sections
define TIMER_CLI_MAKE_HELP
makefile targets:
    help            show this message
    lint            dry run linters
    dolint          apply linter changes
    venv            poetry install dependencies into venv
    requirements    generate `poetry.lock` file
    install         install dependencies and package
endef
export TIMER_MAKE_HELP

.PHONY: help test test-coverage install lint dolint run docker

help:
	@echo "$$TIMER_MAKE_HELP"

venv:
	poetry update
	poetry install

poetry.lock: pyproject.toml
	poetry lock

requirements.txt: poetry.lock
	poetry export -f requirements.txt > requirements.txt

requirements: requirements.txt

install: venv requirements

lint: poetry.lock
	- poetry run isort --check-only $(ISORT_OPTS) $(LINT_PATHS)
	- poetry run black --check $(LINT_PATHS)

dolint: poetry.lock
	poetry run isort $(ISORT_OPTS) $(LINT_PATHS)
	poetry run black $(LINT_PATHS)
