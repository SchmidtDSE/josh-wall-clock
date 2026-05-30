# Benchmark Results — Josh vs. Mesa (ForeverTree)

Wall-clock comparison of the Josh (JVM/BigDecimal) and Mesa (Python/Decimal)
ForeverTree simulations, each run in single-threaded and multi-threaded modes.

## How these were produced

- **Fleet:** 10 × `m7i.2xlarge` (8 vCPU, 32 GiB) on AWS EC2, Ubuntu 24.04.
- **Per machine:** all four configurations run once at **100 replicates** via
  [`run_all.sh`](../run_all.sh), bootstrapped by [`setup.sh`](../setup.sh) and
  orchestrated by [`deploy/fleet.sh`](../deploy/fleet.sh).
- Josh's `.jshd` preprocessing is built once (untimed) and reused by both Josh
  configs; each implementation also gets an untimed warm-up before timing.
- 10 machines × 4 configs = **40 data points** (`all_results.csv`).

### The four configurations

| implementation | threaded | description |
|---|---|---|
| josh | false | `--serial-patches` (single-threaded) |
| josh | true  | parallel patches (default) |
| mesa | false | CPython 3.12 (with GIL), `forevertree.py` |
| mesa | true  | free-threaded CPython 3.14t (no-GIL), `forevertree_threaded.py` |

## Summary (mean across 10 machines)

| config | mean wall | min | max | stddev | mean CPU-sec (user) |
|---|---:|---:|---:|---:|---:|
| josh threaded | **595.2s** | 548.1 | 639.0 | 29.7 | 3918.7 |
| mesa threaded | 1033.5s | 961.7 | 1138.8 | 66.8 | 6073.5 |
| josh serial | 1521.4s | 1420.8 | 1640.4 | 82.0 | 2892.3 |
| mesa serial | 1886.4s | 1728.1 | 2135.5 | 136.4 | 1886.1 |

## Takeaways

- **Josh is faster in every comparison.** Threaded: 1.74× faster wall-clock
  (595s vs 1034s). Serial: 1.24× faster (1521s vs 1886s).
- **Threading speedup** (serial → threaded): Josh **2.56×**, Mesa **1.83×**.
- **CPU efficiency:** Mesa's free-threading burns far more cores for less gain —
  Mesa threaded uses 6074 CPU-sec to Josh's 3919, yet is still slower. Mesa's
  1.83× speedup costs ~3.2× the CPU (1886 → 6074 user-sec), indicating heavy
  free-threading/synchronization overhead.
- **Sanity checks pass:** `mesa serial` user ≈ wall (1886 ≈ 1886) → genuinely
  single-core; `josh serial` runs ~1.9 cores (2892 / 1521) from background JVM
  GC/JIT threads.
- Cross-machine variance is low (stddev 2–7% of mean), so the 10-machine
  estimate is stable.

## Files

- `all_results.csv` — all 40 raw data points, sorted by config then host.
- `summary.csv` — per-config aggregates (n, mean/min/max/stddev wall, mean user).

Columns: `hostname,implementation,threaded,replicates,cores,wallSeconds,userSeconds`.

## Reproducing

```bash
export REGION=us-east-2
export REPO_URL=https://github.com/SchmidtDSE/josh-wall-clock.git
./deploy/fleet.sh up        # launch 10 × m7i.2xlarge
./deploy/fleet.sh run       # bootstrap + run all four configs at 100 replicates
./deploy/fleet.sh status    # poll until every host reports DONE
./deploy/fleet.sh collect && ./deploy/fleet.sh merge
./deploy/fleet.sh down      # terminate the fleet (stops billing)
```
