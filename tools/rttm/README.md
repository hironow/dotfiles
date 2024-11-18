# rttm

RTTM file tool for [ELAN](https://archive.mpi.nl/tla/elan).

```shell
# Convert RTTM to EAF.
mx uv run python to_eaf.py sample.rttm output.eaf

# Visualize RTTM.
mx uv run python visualize.py sample.rttm -o output.png

# fmt.
mx uv run ruff check --select I --fix && ruff format  
```
