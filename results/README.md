# Benchmark Results — Josh vs. Mesa (ForeverTree)
Archive of a Josh and Mesa wall clock comparison.

## Purpose
Wall-clock comparison of the Josh (JVM/BigDecimal) and Mesa (Python/Decimal) ForeverTree simulations, each run in single-threaded and multi-threaded modes. These are cached results from a cluster-based run.

## Conditions

- **Fleet:** 40 × `m7i.2xlarge` (8 vCPU, 32 GiB) on AWS EC2, Ubuntu 24.04.
- **One config per machine:** each of the four configurations runs on its own
  set of **10 machines** (assigned round-robin), once at **100 replicates** via
  [`run_all.sh`](../run_all.sh), bootstrapped by [`setup.sh`](../setup.sh) and
  orchestrated by [`deploy/fleet.sh`](../deploy/fleet.sh). Isolating one config
  per box means configs never compete for cores on the same machine.
- **Simulation:** 101 annual timesteps (years 2024–2124), driven by the
  synthetic climate data in [`data/`](../data) (101-year span, 31 × 50 grid).
- Josh's `.jshd` preprocessing is built fresh inside each Josh timing (one
  preprocess per config, amortized across the replicates); each implementation
  also gets an untimed warm-up before timing.
- 4 configs × 10 machines = **40 data points** (`all_results.csv`).

### The four configurations

| implementation | threaded | description |
|---|---|---|
| josh | false | `--serial-patches` (single-threaded) |
| josh | true  | parallel patches (default) |
| mesa | false | CPython 3.12 (with GIL), `forevertree.py` |
| mesa | true  | free-threaded CPython 3.14t (no-GIL), `forevertree_threaded.py` |

## Summary (mean across 10 machines per config)

| config | mean wall | min | max | stddev | mean CPU-sec (user) |
|---|---:|---:|---:|---:|---:|
| josh threaded | **5054.3s** (84.2 min) | 4745.7 | 5357.4 | 216.2 | 35341.9 |
| mesa threaded | 9209.9s (153.5 min) | 8308.4 | 10170.5 | 541.2 | 56100.8 |
| josh serial | 12862.9s (214.4 min) | 11862.1 | 13755.0 | 586.9 | 26398.2 |
| mesa serial | 16654.9s (277.6 min) | 15798.0 | 18241.2 | 884.2 | 16640.9 |

## Takeaways

- **Josh is faster in every comparison.** Threaded: 1.82× faster wall-clock (5054s vs 9210s). Serial: 1.29× faster (12863s vs 16655s).
- **Threading speedup** (serial → threaded): Josh **2.54×**, Mesa **1.81×**.
- **CPU efficiency:** Mesa's free-threading burns far more cores for less gain. Mesa threaded uses 56101 CPU-sec to Josh's 35342. Mesa's 1.81× speedup costs ~3.4× the CPU (16641 to 56101 user-sec), indicating heavy free-threading/synchronization overhead.
- **Sanity checks pass:** `mesa serial` user approx wall (16641 approx 16655) as it is genuinely single-core. Note `josh serial` runs ~2.0 cores (26398 / 12863) from background JVM GC/JIT threads.
- Cross-machine variance is low (stddev 4–6% of mean), so the 10-machine estimate is stable.

## Files

- `all_results.csv` — all 40 raw data points, sorted by config then host.
- `summary.csv` — per-config aggregates (n, mean/min/max/stddev wall, mean user).

Columns: `hostname,implementation,threaded,replicates,cores,wallSeconds,userSeconds`. See root README.

## Usage

```bash
export REGION=us-east-2
export REPO_URL=https://github.com/SchmidtDSE/josh-wall-clock.git
./deploy/fleet.sh up        # launch 40 × m7i.2xlarge
./deploy/fleet.sh run       # bootstrap + run one config per host at 100 replicates
./deploy/fleet.sh status    # poll until every host reports DONE
./deploy/fleet.sh collect && ./deploy/fleet.sh merge
./deploy/fleet.sh down      # terminate the fleet (stops billing)
```
