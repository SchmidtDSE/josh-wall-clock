# Mesa reference implementation
Implementation of the ForeverTree model in Python using Mesa.

## Purpose
The Python/[Mesa](https://mesa.readthedocs.io/stable/) side of the ForeverTree wall-clock benchmark. It grows a grid of tree agents over yearly timesteps, where each tree's annual height increment is driven by gridded temperature and precipitation read from the synthetic NetCDF climate in [`../data/`](../data). Every model quantity is carried as a native 64-bit float so the comparison against [Josh](../reference) (run with `--use-float-64`) isolates runtime and threading behavior rather than numeric representation.

## Files

- `forevertree.py` — serial baseline. Defines the `ForeverTree` agent and
  `ForeverTreeModel`, the growth math, and the per-process climate cache. Run
  directly to produce one CSV per replicate.
- `forevertree_threaded.py` — free-threaded (no-GIL) variant. Reuses everything
  from `forevertree.py` and overrides only the per-step loop so the independent
  patches in a step run across a thread pool. Meant for a free-threaded CPython
  build (`python3.14t`) with `PYTHON_GIL=0`.
- `run.sh` — launch the serial model (prefers `./.venv`).
- `run-ft.sh` — launch the threaded model on the free-threaded interpreter
  (prefers `./.venv-ft`, exports `PYTHON_GIL=0`).
- `requirements.txt` — pinned dependencies (mesa, numpy, pandas, xarray,
  netCDF4).

## Usage
The two virtualenvs are normally provisioned by the top-level [`setup.sh`](../setup.sh): `.venv` on CPython 3.12 for the serial config and `.venv-ft` on free-threaded 3.14t for the threaded config.

```sh
./run.sh [replicates]              # serial; -> output/results_<seed>.csv
./run-ft.sh [replicates] [threads] # threaded; -> output/results_threaded_<seed>.csv
```

Both scripts honor `PYTHON=/path/to/python` to override the interpreter. Each replicate is produced inside one long-lived process so interpreter and import startup is paid once, mirroring how Josh emits all replicates from a single JVM.

## Output
One CSV per replicate under `output/`, with one row per populated grid cell per year: `cell_id, year, nTrees, meanAge, meanHeight, temperature, precipitation`. See root README for details.
