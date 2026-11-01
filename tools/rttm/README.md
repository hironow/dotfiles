# RTTM Tool

Converts RTTM (Rich Transcription Time Marked) files to the ELAN Annotation
Format (EAF) for [ELAN](https://archive.mpi.nl/tla/elan), and plots them,
including speaker overlaps.

It is its own uv project (Python 3.11+). Run the commands from `tools/rttm/`.

## Usage

```shell
uv run --frozen python to_eaf.py input.rttm output.eaf
uv run --frozen python visualize.py input.rttm -o output.png
```

`visualize.py --font <family>` sets the font. The default is "Hiragino Sans"
on macOS and "Noto Sans CJK JP" elsewhere.

## Development

From the repository root:

```shell
just rttm-fmt     # format
just rttm-check   # Ruff, ty, and tests (headless plotting)
```

The root `just fmt`, `just lint`, and `just check` also cover this project.
`pyproject.toml` explains the lint pins (moved by `just bump-tool`), the
dependency quarantine, and the local ty scope.
