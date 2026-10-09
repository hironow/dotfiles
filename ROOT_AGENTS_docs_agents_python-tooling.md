# Python Tooling

Read this when you write or change Python. Use `uv` for packages (AGENTS.md).

## Required tools: these three, no substitutes

- **uv** — packages and runner (`uv sync`, `uv add`, `uv add --dev`, `uv run`, `uvx`)
- **ruff** — linting and formatting (replaces flake8 / black / isort)
- **ty** — static type checking (https://github.com/astral-sh/ty; replaces
  mypy / pyright)

Every Python project uses all three. Pin ruff and ty in a `lint` dependency
group (`uv add --group lint --bounds exact ruff ty`) and wire them into
`just fmt` / `just lint`. Do not add another package manager, linter,
formatter, or type checker.
Ruff and ty are Class 1 (docs/agents/dependency-policy.md). Pin them
**exactly** (one version, adopt new releases aggressively). Pair the seven-day uv
cooldown with `exclude-newer-package = { ruff = false, ty = false }` so the pin
can move. Do not copy a version number into this file; it goes stale. Wire the
gate with this justfile split. The split matters: ruff only parses source, but
ty **resolves imports**:

```just
fmt:
    uv run --locked --only-group lint ruff format .

lint:
    uv run --locked --only-group lint ruff check .
    uv run --locked --only-group lint ruff format --check .
    uv run --locked --group lint ty check
```

Never "fix" ty's `unresolved-import` by silencing the rule. It means ty cannot
see the project's dependencies and is checking nothing. Give ty the
dependencies instead (`--group lint`, not `--only-group`). Keep one ruff.toml /
ty.toml shape per *project*; change only the project's own path and exclude
blocks.

## ruff configuration (canonical — in `pyproject.toml`)

Do **not** change this without explicit human approval. Never relax it to
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
    "PTH",  # flake8-use-pathlib: pathlib over os.path / bare open()
    # "DOC", # pydoclint
    # "D",   # pydocstyle
    "RUF",  # Ruff-specific rules
    "ANN",  # flake8-annotations: every def annotated (ty has no strict mode)
]
extend-ignore = ["E501", "RUF002", "RUF003"]
```

## ty

- All code has type annotations. ruff's `ANN` rules above enforce this,
  because ty has no `--strict`: `[tool.ty.terminal] error-on-warning = true`
  only raises severity; it adds no checks.
- `uv run ty check` must pass with zero diagnostics before you commit.
- Configure ty under `[tool.ty]` in `pyproject.toml`. Raise rule levels; never
  lower them to silence a finding.
- Avoid `# ty: ignore[rule]`. If you cannot avoid it, add a one-line comment
  that explains why.

## Refactoring rules (Python only)

- Put imports at the top of the file, never inside a function or method body.
- Use `pathlib.Path` for paths; `os.path` is deprecated here.
- Iterate a dict as `for key in d`, not `for key in d.keys()`.
- Combine several context managers with the parenthesized form from 3.10.
- All code follows the ruff and ty rules above.

## Pre-commit sequence

```sh
just check  # the full gate; or piecewise (format before linting):
just fmt    # uv run ruff format .
just lint   # uv run ruff check .  &&  uv run ty check
just semgrep   # when .semgrep/ exists
just test   # uv run pytest
```

(The `format-after-edit` hook already runs `ruff format` + `ruff check --fix`
on each edited `.py` file, so most violations are fixed before you commit.)

## External data and encoding

All text you process in the repo must be strict UTF-8. When a fetched web page
or an external file is unreadable, convert it from a legacy Japanese encoding
right away with `iconv` (POSIX standard, pre-installed):

```sh
iconv -f SHIFT-JIS -t UTF-8 input > output
iconv -f EUC-JP   -t UTF-8 input > output
```
