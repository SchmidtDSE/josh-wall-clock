# Continuous integration helpers

Fast smoke-test scripts used by the GitHub Actions workflows in
[`../.github/workflows/`](../.github/workflows). They run each benchmark
configuration end-to-end at a tiny scale (default 2 replicates, a single
timestep) purely to prove it still executes and writes output. **These are not
timing benchmarks** — for real measurements see [`../run_all.sh`](../run_all.sh)
and [`../deploy/`](../deploy).

The reference models are left untouched: Mesa overrides the step count at
runtime, and Josh (which has no CLI step limit) runs against a temporary 1-step
copy of `forevertree.josh` that is restored on exit.

## Files

- `quick_check.sh` — dispatcher for one config. Provisions missing tooling on
  demand (downloads the Josh jar, creates the `uv` venvs mirroring
  [`../setup.sh`](../setup.sh)), runs the config, and verifies an output CSV was
  written.
- `quick_mesa.py` — imports the real Mesa reference modules unchanged, forces
  `NUM_STEPS` down to 1, and delegates to their `main()`.

## Usage

```sh
ci/quick_check.sh <config> [replicates]
#   config = josh-serial | josh-threaded | mesa-serial | mesa-threaded
#   replicates defaults to 2
```

Requires `java` (Josh configs) and `uv` (Mesa configs) on `PATH`; both are
installed by the workflows via hash-pinned setup actions, or locally by
[`../setup.sh`](../setup.sh).

## Workflows

- [`quick-check.yml`](../.github/workflows/quick-check.yml) — runs `quick_check.sh`
  once per config via a build matrix.
- [`draw-hist.yml`](../.github/workflows/draw-hist.yml) — renders
  [`../draw_hist.py`](../draw_hist.py) from the committed results and uploads the
  PNG as an artifact.
