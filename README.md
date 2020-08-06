# `timer_cli`

(See also the PyPI-specific README in README.rst.)

## Installation

Users can install with pip:
```bash
pip install globus-timer-cli
```
Make sure to install in a virtual environment or with the `--user` flag as necessary.

## Development

The CLI is built on `click`; documentation for `click` is found
[here](https://click.palletsprojects.com/en/7.x/).

The project uses [poetry](https://python-poetry.org/) for dependency management.
To install the CLI for development we recommend using poetry.

### Install

Poetry should handle everything:
```bash
poetry install
```

### Usage

Run the CLI with `poetry run timer ...`:
```bash
poetry run timer --help
poetry run timer job --help
```
