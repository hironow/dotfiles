# Python Tooling

Read this when writing or changing Python. Package management is `uv` (AGENTS.md).

## Required tools

- **ruff** — linting + formatting
- **mypy** — static type checking (strict where possible)
- **uv** — packages (`uv sync`, `uv add`, `uv add --dev`, `uv run`)

## ruff configuration (canonical — in `pyproject.toml`)

Do **not** modify this without explicit human approval, and never relax it to
silence a finding.

```toml
[tool.ruff.lint]
# see: https://docs.astral.sh/ruff/rules/
select = [
    "FAST", # FastAPI
    "C90",  # mccabe
    "NPY",  # numpy
    "PD",   # pandas
    "B",    # flake8-bugbear
    "A",    # flake8-builtins
    "DTZ",  # flake8-datetimez
    "T20",  # flake8-print
    "N",    # pep8-naming
    "I",    # isort
    "E",    # pycodestyle errors
    "F",    # Pyflakes
    "PLE",  # Pylint errors
    "PLR",  # Pylint refactor
    "UP",   # pyupgrade
    "FURB", # refurb
    # "DOC", # pydoclint
    # "D",   # pydocstyle
    "RUF",  # Ruff-specific rules
]
extend-ignore = ["E501", "RUF002", "RUF003"]
```

## mypy

- All code is type-annotated.
- mypy passes with zero errors before commit.
- Strict mode where possible.
- Avoid `# type: ignore`; if unavoidable, add a one-line justification comment.

## Refactoring rules (Python-specific)

- Imports at the top of the file — never inside function/method bodies.
- Use `pathlib.Path` for path manipulation; `os.path` is deprecated here.
- Iterate dicts as `for key in d`, not `for key in d.keys()`.
- Combine multiple context managers with 3.10+ parenthesized form.
- All code conforms to the ruff + mypy rules above.

## Pre-commit sequence

```sh
just check  # the full gate; or piecewise (format before linting):
just fmt    # uv run ruff format .
just lint   # uv run ruff check .  &&  uv run mypy .
just semgrep   # when .semgrep/ exists
just test   # uv run pytest
```

(The `format-after-edit` hook already runs `ruff format` + `ruff check --fix`
on each edited `.py` file, so most violations are fixed before you reach commit.)

## External data & encoding

All text processed in-repo must be strict UTF-8. Convert legacy Japanese
encodings with `iconv` (POSIX-standard, pre-installed) the moment a web-fetched
page or external file is unreadable:

```sh
iconv -f SHIFT-JIS -t UTF-8 input > output
iconv -f EUC-JP   -t UTF-8 input > output
```
