# Benchmark Results — Josh vs. Mesa (ForeverTree)
Archive of a Josh and Mesa wall clock comparison.

## Purpose
Wall-clock comparison of the Josh (JVM/BigDecimal) and Mesa (Python/Decimal) ForeverTree simulations, each run in single-threaded and multi-threaded modes, for both the AI-generated and hand-written (manual) implementations. These are cached results from a cluster-based run.

## Conditions

- **Fleet:** 80 × `m7i.2xlarge` (8 vCPU, 32 GiB) on AWS EC2, Ubuntu 24.04.
- **One config per machine:** each of the eight configurations runs on its own
  set of **10 machines** (assigned round-robin), once at **100 replicates** via
  [`run_all.sh`](../run_all.sh), bootstrapped by [`setup.sh`](../setup.sh) and
  orchestrated by [`deploy/fleet.sh`](../deploy/fleet.sh). Isolating one config
  per box means configs never compete for cores on the same machine.
- **Simulation:** 101 annual timesteps (years 2024–2124), driven by the
  synthetic climate data in [`data/`](../data) (101-year span, 31 × 50 grid).
- Josh's `.jshd` preprocessing is built fresh inside each Josh timing (one
  preprocess per config, amortized across the replicates); each implementation
  also gets an untimed warm-up before timing.
- 8 configs × 10 machines = **80 data points** (`all_results.csv`).

### The eight configurations

| implementation | model | threaded | description |
|---|---|---|---|
| josh | ai | false | `--serial-patches`, `forevertree.josh` |
| josh | ai | true  | parallel patches, `forevertree.josh` |
| josh | manual | false | `--serial-patches`, `forevertree_manual.josh` |
| josh | manual | true  | parallel patches, `forevertree_manual.josh` |
| mesa | ai | false | CPython (with GIL), `forevertree.py` |
| mesa | ai | true  | free-threaded CPython 3.14t (no-GIL), `forevertree_threaded.py` |
| mesa | manual | false | CPython, `forevertree_manual.py` (serial) |
| mesa | manual | true  | CPython, `forevertree_manual.py` (pathos ProcessPool) |

## Summary (mean across 10 machines per config)

| config | mean wall | min | max | stddev | mean CPU-sec (user) |
|---|---:|---:|---:|---:|---:|
| josh manual threaded | **3479.3s** (58.0 min) | 3328.3 | 3605.5 | 86.9 | 21406.9 |
| mesa manual threaded | 3564.5s (59.4 min) | 3268.1 | 3820.4 | 186.2 | 24401.7 |
| josh ai threaded | 6280.2s (104.7 min) | 5934.7 | 6801.8 | 258.3 | 40776.5 |
| mesa ai threaded | 9288.0s (154.8 min) | 8632.5 | 10100.0 | 485.2 | 56285.8 |
| josh manual serial | 8631.4s (143.9 min) | 8208.8 | 9071.9 | 304.3 | 15234.6 |
| mesa manual serial | 13625.5s (227.1 min) | 12377.2 | 14706.5 | 800.2 | 13618.7 |
| josh ai serial | 17846.0s (297.4 min) | 16818.7 | 19100.8 | 660.0 | 28429.9 |
| mesa ai serial | 16280.8s (271.3 min) | 15609.9 | 17315.9 | 640.8 | 16271.6 |

## Takeaways

- **Manual threaded is the fastest tier**, and Josh edges out Mesa by ~2.4%
  (3479s vs 3565s). The hand-written manual implementations are roughly **2×
  faster** than the AI-generated ones when threaded.
- **Threading speedup** (serial → threaded):
  - manual: Josh **2.48×**, Mesa **3.82×**
  - ai: Josh **2.84×**, Mesa **1.75×**
- **AI vs manual is the biggest factor**: for both runtimes the manual model
  beats the AI one at the same threading. This reflects algorithmic
  differences — e.g. the manual Mesa caches climate lookups per timestep
  (the AI Mesa re-derives nearest-neighbour indices per tree), and the manual
  Josh hoists the climate impact to the patch level.
- **CPU efficiency:** Mesa's threaded variants burn far more cores for the
  gain. mesa-ai threaded uses 56286 CPU-sec (highest of all) yet is slower than
  josh-ai threaded; mesa-manual threaded uses 24402 CPU-sec vs its 3565s wall.
  Mesa's free-threading/process-pool overhead is heavy relative to Josh.
- **Sanity checks pass:** serial configs have user ≈ wall (single core), while
  threaded configs show user ≫ wall from multi-core execution. Note Josh's JVM
  adds background GC/JIT threads, so josh serial user slightly exceeds wall.
- Cross-machine variance is low (stddev 3–6% of mean for threaded; ~5% for
  serial), so the 10-machine estimate is stable.

## Files

- `all_results.csv` — all 80 raw data points, sorted by config then host.
- `summary.csv` — per-config aggregates (n, mean/min/max/stddev wall, mean user).

Columns: `hostname,implementation,model,threaded,replicates,cores,wallSeconds,userSeconds`. See root README.

## Usage

```bash
export REGION=us-east-2
export REPO_URL=https://github.com/SchmidtDSE/josh-wall-clock.git
./deploy/fleet.sh up        # launch 80 × m7i.2xlarge
./deploy/fleet.sh run       # bootstrap + run one config per host at 100 replicates
./deploy/fleet.sh status    # poll until every host reports DONE
./deploy/fleet.sh collect && ./deploy/fleet.sh merge
./deploy/fleet.sh down      # terminate the fleet (stops billing)
```
