# Josh wall-clock profile

A small, self-contained harness for comparing the wall-clock (and user-CPU)
cost of the same ForeverTree vegetation model on two runtimes that both use
arbitrary-precision decimal arithmetic:

- **Josh** (`reference/`) — the Josh DSL on the JVM, which carries every model
  quantity as a Java `BigDecimal`.
- **Mesa** (`reference-mesa/`) — a Python/Mesa implementation whose per-tree
  growth math runs entirely in Python's `Decimal` (the `BigDecimal` analogue).

Each implementation produces all replicates inside a single process — one JVM
for Josh, one long-lived Python interpreter for Mesa — so process startup is
paid once per test on both sides.

## Layout

```
.
├── benchmark.sh              # the profiler (times both, writes a CSV)
├── joshsim-fat.jar           # Josh runtime (auto-downloaded if missing)
├── data/                     # synthetic climate inputs (NetCDF)
├── reference/                # Josh implementation
│   ├── forevertree.josh
│   └── run.sh                # ./run.sh [replicates]
└── reference-mesa/           # Mesa/Decimal implementation
    ├── forevertree.py        # python forevertree.py [replicates]
    ├── run.sh                # ./run.sh [replicates]
    └── requirements.txt
```

## Setup

Requires Java (for the Josh jar), Python **3.12** (the pinned mesa 3.5.1
requires ≥3.12), and `curl`. Easiest path is [uv][uv], which provisions the
interpreter for you:

```sh
# Python environment for the Mesa side
cd reference-mesa
uv venv --python 3.12 .venv          # downloads CPython 3.12 if needed
VIRTUAL_ENV=.venv uv pip install -r requirements.txt
cd ..
```

Without uv, any Python ≥3.12 works:

```sh
cd reference-mesa
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cd ..
```

(`reference-mesa/run.sh` uses `./.venv/bin/python` if present, else the system
`python3`; override with `PYTHON=/path/to/python`.)

The Josh jar is fetched automatically by `benchmark.sh` from
`https://www.joshsim.org/dist/dev/joshsim-fat.jar` if it isn't already present.
The first Josh run also preprocesses the climate inputs into `.jshd` files
(cached thereafter).

[uv]: https://docs.astral.sh/uv/

## Running the benchmark

```sh
./benchmark.sh [replicates] [iterations] [output_file]
```

- `replicates` — replicates produced per test run (default `1`).
- `iterations` — number of timed test runs per implementation (default `10`).
- `output_file` — destination CSV (default `benchmark_results_<timestamp>.csv`).

Example (10 single-replicate tests per implementation):

```sh
./benchmark.sh 1 10
```

Each iteration times three configurations: Josh with threading (parallel
patches, the default), Josh without threading (`--serial-patches`), and Mesa
(single-threaded Python/Decimal).

### Output

A tidy ("long") CSV, one row per timed test run:

```csv
implementation,replicates,threaded,wallClockSeconds,userTimeSeconds
josh,1,true,12.430,38.512
josh,1,false,20.156,21.880
mesa,1,false,29.749,29.310
...
```

`wallClockSeconds` is elapsed real time; `userTimeSeconds` is user-mode CPU
time summed across all threads — so for threaded Josh, `userTimeSeconds` can
exceed `wallClockSeconds` when work runs on multiple cores.

## A note on JIT

The timed loop spawns a fresh process every iteration, so the JVM's JIT starts
cold each test and never carries warming across iterations. Where JIT *does*
accumulate is across replicates *within* one test (a single JVM invocation):
the hot `BigDecimal` paths get C2-compiled and later replicates run faster.
Python's `Decimal` is implemented in C (`libmpdec`) and runs at constant native
speed regardless, so it shows no analogous warm-up. To see the JIT effect,
sweep `replicates` and compare per-replicate amortized time across the two.
