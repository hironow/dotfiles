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
mx uv run python to_eaf.py input.rttm output.eaf
```

### Visualize RTTM

```shell
mx uv run python visualize.py input.rttm -o output.png
```

Optional arguments:
- `--font`: Specify a font family (e.g., "Arial"). Defaults to "Hiragino Sans" on macOS and "Noto Sans CJK JP" elsewhere.

### Development

Format and lint code:

```shell
mx uv run ruff check . --fix
mx uv run ruff format .
```
