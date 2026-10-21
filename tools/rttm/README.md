# RTTM Tool

RTTM (Rich Transcription Time Marked) file tool for [ELAN](https://archive.mpi.nl/tla/elan).

## Features

- **Convert RTTM to EAF**: Converts RTTM files to ELAN Annotation Format (EAF).
- **Visualize RTTM**: Generates a visualization of the RTTM data, including speaker overlaps.

## Requirements

- Python 3.11+
- Dependencies are managed via `uv`.

## Usage

### Convert RTTM to EAF

```shell
uv run --frozen python to_eaf.py input.rttm output.eaf
```

### Visualize RTTM

```shell
uv run --frozen python visualize.py input.rttm -o output.png
```

Optional arguments:

- `--font`: Specify a font family (e.g., "Arial"). Defaults to "Hiragino Sans" on macOS and "Noto Sans CJK JP" elsewhere.

### Development

From the repository root:

```shell
just rttm-fmt        # formatting
just rttm-check      # Ruff, ty, and tests (headless plotting)
```

The root `just fmt`, `just lint`, and `just check` also reach the RTTM project.
Ruff and ty live in the `lint` dependency group with exact pins matching root,
emulator, and mise; `just bump-tool ruff|ty VERSION` updates all declarations
and all three uv locks. Other dependencies retain the seven-day quarantine.
The RTTM-local ty configuration checks the CLI files and tests with the
application dependencies available; it does not inherit root's scripts/tests-only scope.
