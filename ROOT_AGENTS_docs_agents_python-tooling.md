# Python Tooling

Read this when writing or changing Python. Package management is `uv` (AGENTS.md).

## Required tools — the trio, no substitutes

- **uv** — packages + runner (`uv sync`, `uv add`, `uv add --dev`, `uv run`, `uvx`)
- **ruff** — linting + formatting (replaces flake8 / black / isort)
- **ty** — static type checking (https://github.com/astral-sh/ty; replaces
  mypy / pyright)

Every Python project uses all three, pinned as dev dependencies
(`uv add --dev ruff ty`) and wired into `just fmt` / `just lint`. Do not
introduce another package manager, linter, formatter, or type checker.
Ruff and ty are Class 1 (docs/agents/dependency-policy.md): pin them
**exactly** (one version, aggressive adoption), pair the seven-day uv
cooldown with `exclude-newer-package = { ruff = false, ty = false }` so
the pin can move, and do not copy a version number into this file — it
goes stale. Wire the gate with this justfile split (load-bearing: ruff
only parses source, ty **resolves imports**):

```just
fmt:
    uv run --locked --only-group lint ruff format .

lint:
    uv run --locked --only-group lint ruff check .
    uv run --locked --only-group lint ruff format --check .
    uv run --locked --group lint ty check
```

Never "fix" ty's `unresolved-import` by silencing the rule — it means ty
cannot see the project's dependencies and is checking nothing. Give it the
deps instead (`--group lint`, not `--only-group`). Keep one ruff.toml /
ty.toml shape per *project*; change only project-local path and exclude
blocks.

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
    "ANN",  # flake8-annotations: every def annotated (ty has no strict mode)
]
extend-ignore = ["E501", "RUF002", "RUF003"]
```

## ty

- All code is type-annotated — enforced by ruff's `ANN` rules above, because ty
  has no `--strict`: `[tool.ty.terminal] error-on-warning = true` only raises
  severity, it adds no checks.
- `uv run ty check` passes with zero diagnostics before commit.
- Configure under `[tool.ty]` in `pyproject.toml`; raise rule levels, never
  lower them to silence a finding.
- Avoid `# ty: ignore[rule]`; if unavoidable, add a one-line justification
  comment.

## Refactoring rules (Python-specific)

- Imports at the top of the file — never inside function/method bodies.
- Use `pathlib.Path` for path manipulation; `os.path` is deprecated here.
- Iterate dicts as `for key in d`, not `for key in d.keys()`.
- Combine multiple context managers with 3.10+ parenthesized form.
- All code conforms to the ruff + ty rules above.

## Pre-commit sequence

```sh
just check  # the full gate; or piecewise (format before linting):
just fmt    # uv run ruff format .
just lint   # uv run ruff check .  &&  uv run ty check
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
