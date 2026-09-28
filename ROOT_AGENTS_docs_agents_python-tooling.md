# Python Tooling

Read this when writing or changing Python. Package management is `uv` (AGENTS.md).

## Required tools — the trio, no substitutes

- **uv** — packages + runner (`uv sync`, `uv add`, `uv add --dev`, `uv run`, `uvx`)
- **ruff** — linting + formatting (replaces flake8 / black / isort)
- **ty** — static type checking (https://github.com/astral-sh/ty; replaces
  mypy / pyright)

Every Python project uses all three, pinned in a `lint` dependency group
(`uv add --group lint ruff ty`) and wired into `just fmt` / `just lint` —
the group is named `lint`, not `dev`, because the recipes below select it
by name (`--only-group lint` / `--group lint`). Do not introduce another
package manager, linter, formatter, or type checker.
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

## ruff configuration (canonical — the org hub's `ruff.toml`)

The rule set is **owned by the org hub**, not by this file: the hub's
`.github` repository, `templates/python/ruff.toml`, read at commit
`6beef76764ac26b17d0051b7893dc3ea393b21a1` (blob
`5305c57bb2bdb99e65c5f3ded07d98811dff47c4`). **If this block and that hub
template ever differ, the hub wins** — re-read the hub and fix this file, do
not adjust the project. Evolve the rule set in the hub, never per repo: a
divergent `select` list is how twelve projects end up with twelve gates.

Consume it by **copying the hub file to the Python project root** (the
directory holding `pyproject.toml`) as `ruff.toml`, adapting only the blocks
the hub marks `ADAPT`. Do **not** transcribe it into `[tool.ruff.lint]` in
`pyproject.toml`: ruff reads *either* `ruff.toml` *or* `[tool.ruff]`, and
when both exist `ruff.toml` silently wins with no warning at any verbosity —
so a project adopting the hub file deletes its `[tool.ruff]*` sections in the
same commit. Inside a `ruff.toml` the keys are top-level (`line-length`,
`[lint]`, `[lint.per-file-ignores]`); `[tool.ruff]` inside a `ruff.toml` is a
hard parse error.

Do **not** modify this without explicit human approval, and never relax it to
silence a finding.

```toml
# ruff.toml — see: https://docs.astral.sh/ruff/rules/
# `target-version` is deliberately absent: ruff derives it from
# `requires-python` in pyproject.toml. Set it here only when the project has
# no pyproject.toml — ruff then falls back to its own default (py310).
line-length = 100

[lint]
select = [
    "FAST", # FastAPI misuse
    "C90",  # mccabe complexity
    "NPY",  # numpy legacy APIs
    "PD",   # pandas foot-guns
    "B",    # flake8-bugbear
    "A",    # flake8-builtins (shadowing a builtin)
    "DTZ",  # flake8-datetimez (naive datetimes)
    "T20",  # flake8-print (stray print/pprint)
    "N",    # pep8-naming
    "I",    # isort
    "E",    # pycodestyle errors
    "F",    # Pyflakes
    "W",    # pycodestyle warnings
    "PLE",  # Pylint errors
    "PLR",  # Pylint refactor
    "UP",   # pyupgrade
    "FURB", # refurb modernisation
    "RUF",  # Ruff-specific rules
    "SIM",  # flake8-simplify
    "C4",   # flake8-comprehensions
    "S110", # bandit: try-except-pass (a SINGLE rule, not the S family)
    "ANN",  # flake8-annotations: every def annotated (ty has no strict mode)
]

ignore = [
    "E501",   # line length is the formatter's job; E501 double-reports it
    "RUF001", # ambiguous unicode in a string    — Japanese prose is not a typo
    "RUF002", # ambiguous unicode in a docstring — ditto
    "RUF003", # ambiguous unicode in a comment   — ditto
    "ANN401", # `Any` in an annotation: `mypy --strict` did not check this
              # either (`disallow_any_explicit` is not part of --strict), so
              # keeping it would be stricter than what ty replaced.
]

# ADAPT (per project). The org's one blanket exception, and only for tests:
# asserting against a literal is a test's entire job. NOT an ANN escape
# hatch — test functions and their fixtures stay annotated.
[lint.per-file-ignores]
"**/tests/**/*.py" = ["PLR2004"]
```

Two deliberate **non**-selections, so nobody "helpfully" adds them later: the
`S` (bandit) *family* — only the single rule `S110` above is on — and `FA`,
whose FA100 demands `from __future__ import annotations` and collides with
the org's banned-api rule against `__future__`. `ANN101`/`ANN102` were
removed in ruff 0.16.x; listing either in `select` is a hard error.

Excluding a **generated** tree (protobuf, codegen, an engine's Python output)
is not weakening the gate — the rule set stays byte-identical, only the set
of files it reads changes. Add it next to the hub file as a top-level
`extend-exclude`, placed **before the first table header** (a bare key after
`[lint]` is parsed as a rule selector), and declare what generates the tree
and the measured effect.

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
