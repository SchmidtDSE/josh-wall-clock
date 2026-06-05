# Josh reference implementation

The [Josh](https://www.joshsim.org/) DSL side of the ForeverTree wall-clock benchmark. Josh is a domain-specific language on the JVM; this directory holds the model definition and a script to run it, timed against the equivalent Python/Mesa model in [`../reference-mesa/`](../reference-mesa).

## Files

- `forevertree.josh` — the model: a 1 km grid over a fixed lat/lon bounding box,
  10 `ForeverTree` organisms per patch, advanced for 101 annual steps (years
  2024–2124). Each tree's yearly growth is the product of a quadratic
  temperature impact, a sigmoid precipitation impact, and a normal stochastic
  term, matching `forevertree.py` in `../reference-mesa/`. The `unit` blocks
  define the `kgm2s → mm` precipitation conversion and the `K`/`year` aliases.
- `run.sh` — preprocess the climate inputs and run the model.

## Usage

`run.sh` expects the Josh fat jar at `../joshsim-fat.jar` (provisioned by the
top-level [`setup.sh`](../setup.sh)). It first preprocesses each NetCDF input in
[`../data/`](../data) into a cached `.jshd` file (`temperature.jshd`,
`precipitation.jshd`) if not already present, then runs the simulation.

```sh
./run.sh [replicates] [threaded]
#   threaded = true  -> parallel patches (default)
#   threaded = false -> --serial-patches (single-threaded)
```

The run passes `--use-float-64` so Josh backs every model quantity with a Java `double`, matching the native float used by the Mesa reference and keeping the wall-clock comparison clean.

## Output

One CSV per replicate under `output/` (`results_<replicate>.csv`), with one row per patch per year: `year, nTrees, meanAge, meanHeight, temperature, precipitation`. See root README for deatils.
