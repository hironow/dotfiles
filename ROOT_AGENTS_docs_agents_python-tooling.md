# Python tooling

Read this when you write or change Python. Use `uv` for packages (AGENTS.md).

## Speed: move the slow part, do not tune Python

Do not do systems-level speed work in Python (C extensions, Cython, shared
memory, lock-free structures). When a Python tool is too slow, measure first
(docs/agents/performance.md), then fix I/O, queries, the call pattern, and the algorithm in Python. Only if
the computation itself still misses the requirement, move that part to Go
(Rust only when Go does not fit; see docs/agents/rust-tooling.md). Existing
Python tooling otherwise stays where it is.

GPU work that targets CUDA, through PyTorch or another CUDA library, is the one
place where new code may be Python (AGENTS.md). There the speed comes from the library on the GPU, so
measure, then fix the data pipeline and how you call the library first.

## Required tools: these three, no substitutes

- **uv** — packages and runner (`uv sync`, `uv add`, `uv add --dev`, `uv run`, `uvx`)
- **ruff** — linting and formatting (replaces flake8 / black / isort)
- **ty** — static type checking (https://github.com/astral-sh/ty; replaces
  mypy / pyright)

Every Python project uses all three. Do not add another package manager,
linter, formatter, or type checker.

- Pin ruff and ty in a `lint` dependency group
  (`uv add --group lint --bounds exact ruff ty`), and wire them into
  `just fmt` / `just lint`.
- Ruff and ty are Class 1 (docs/agents/dependency-policy.md). Pin them
  **exactly** (one version, adopt new releases aggressively).
- Pair the seven-day uv cooldown with
  `exclude-newer-package = { ruff = false, ty = false }` so the pin can move.
- Do not copy a version number into this guide; it goes stale.

Wire the gate with this justfile split. The split matters: ruff only parses
source, but ty **resolves imports**:

```just
fmt:
    uv run --locked --only-group lint ruff format .

lint:
    uv run --locked --only-group lint ruff check .
    uv run --locked --only-group lint ruff format --check .
    uv run --locked --group lint ty check --python-platform win32
    uv run --locked --group lint ty check --python-platform linux
    uv run --locked --group lint ty check --python-platform darwin
```

Never "fix" ty's `unresolved-import` by silencing the rule. It means ty cannot
see the project's dependencies and is checking nothing. Give ty the dependencies
instead (`--group lint`, not `--only-group`). Keep one ruff and ty config shape
per *project* (`ruff.toml` / `ty.toml`, or the `pyproject.toml` tables below);
change only the project's own path and exclude blocks.

### One ty run per OS

The full gate (`just check`, which CI and the pre-commit hook run) runs ty
once per OS the code runs on. ty narrows `sys.platform` and `os.name` to the
`--python-platform` it checks for, so a branch for another OS is checked only
when ty checks for that OS. Tooling that runs on developer machines runs on all
three; a service deployed only to Linux needs only `linux`. Remove a line only
for an OS the code never runs on, never to hide a finding.

- Write an OS branch as a `sys.platform` comparison. It tells Linux from
  macOS, and typeshed keys OS-only APIs on it.
- A name imported under an OS condition does not exist when ty checks for
  another OS. There, an annotation that names it is an error, and code that
  uses it is not checked at all.
- Import a module of your own that runs only on some OSes under
  `if TYPE_CHECKING or sys.platform != "win32":`, so every OS's check reads
  its types. Inside it, guard each OS-only call the same way as below.
- A standard-library module that exists only on some OSes (`fcntl`, `pwd`,
  `grp`, `winreg`, `msvcrt`) has no members when ty checks for another OS,
  even under `TYPE_CHECKING`. Use its names only after a `sys.platform` check
  in the same function, and keep its types out of signatures every OS reads.
- When a test body calls an API another OS lacks, skip in the body
  (`if sys.platform == "win32": pytest.skip(...)`), not with `skipif`: ty
  does not narrow on a marker.
- If ty cannot resolve an import that only another OS installs, stop and ask
  the human. Do not remove that OS's line or silence the rule.
- These checks find type errors. Only running the tests on an OS shows how
  the code behaves there.

## ruff configuration (canonical — in `pyproject.toml`)

Change this only with explicit human approval. Never relax it to
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
- `uv run ty check` must pass with zero diagnostics for every OS the code runs on
  before you commit (see "One ty run per OS").
- Configure ty under `[tool.ty]` in `pyproject.toml`. Raise rule levels; never
  lower them to silence a finding.
- Avoid `# ty: ignore[rule]`. If you cannot avoid it, add a one-line comment
  that explains why.

## Refactoring rules (Python only)

- Put imports at the top of the file, never inside a function or method body.
- Iterate a dict as `for key in d`, not `for key in d.keys()`.
- Combine several context managers with the parenthesized form from 3.10.

## External data and encoding

All text you process in the repo must be strict UTF-8. When a fetched web page
or an external file is unreadable, convert it from a legacy Japanese encoding
right away with `iconv` (POSIX standard, pre-installed), for example
`iconv -f SHIFT-JIS -t UTF-8 input > output` (or `-f EUC-JP`).
