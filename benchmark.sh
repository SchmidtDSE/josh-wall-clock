#!/usr/bin/env bash
#
# Wall-clock + user-CPU benchmark: Josh vs Mesa, across the ai and manual
# implementations, in threaded and non-threaded modes.
#
# Each "test" runs one implementation with a given number of replicates, all
# inside a single process (one JVM for Josh, one Python interpreter for Mesa).
# This script runs that test ITERATIONS times per configuration, measuring
# each test's wall-clock and user-CPU time, and appends one row per test to a
# CSV with columns:
#   implementation,model,replicates,threaded,wallClockSeconds,userTimeSeconds
#
# Eight configurations are timed each iteration:
#   josh  ai      threaded=true  (parallel patches)
#   josh  ai      threaded=false (--serial-patches)
#   josh  manual  threaded=true
#   josh  manual  threaded=false
#   mesa  ai      threaded=false (serial)
#   mesa  ai      threaded=true  (free-threaded 3.14t no-GIL)
#   mesa  manual  threaded=false (serial, forevertree_manual.py)
#   mesa  manual  threaded=true  (pathos ProcessPool)
#
# Josh's .jshd preprocessing is rebuilt fresh before each timed Josh run, so the
# preprocess pass is included in the measured time. It is kept across the N
# replicates within a single run, never rebuilt between them.
#
# Both implementations carry every per-tree quantity in arbitrary-precision
# decimal arithmetic -- Josh via Java BigDecimal, Mesa via Python's Decimal --
# so this is an apples-to-apples comparison of the same numeric workload.
#
# Usage:
#   ./benchmark.sh [replicates] [iterations] [output_file]
#
#   replicates    replicates produced per test run (default: 1)
#   iterations    number of timed test runs per implementation (default: 10)
#   output_file   destination CSV (default: benchmark_results_<timestamp>.csv)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
JOSH_RUN="$SCRIPT_DIR/reference/run.sh"
MESA_RUN="$SCRIPT_DIR/reference-mesa/run.sh"
JAR="$SCRIPT_DIR/joshsim-fat.jar"
JAR_URL="https://www.joshsim.org/dist/freeze/josh-wall-clock-snapshot-202608.jar"

REPLICATES="${1:-1}"
ITERATIONS="${2:-10}"
OUT_FILE="${3:-$SCRIPT_DIR/benchmark_results_$(date +%Y%m%d_%H%M%S).csv}"

# Fetch the Josh runtime jar on demand if it isn't already here.
if [ ! -f "$JAR" ]; then
  echo "joshsim-fat.jar not found at $JAR"
  echo "Downloading from $JAR_URL ..."
  curl -fSL "$JAR_URL" -o "$JAR"
  echo "Downloaded ($(du -h "$JAR" | cut -f1))."
fi

# Time one invocation, echoing "<wallSeconds> <userSeconds>". Uses bash's
# `time` keyword with a custom TIMEFORMAT: %R = real (wall), %U = user CPU.
time_run() {
  local tf real user
  tf=$(mktemp)
  { TIMEFORMAT='%R %U'; time "$@" >/dev/null 2>&1; } 2>"$tf"
  read -r real user < "$tf"
  rm -f "$tf"
  printf '%s %s' "$real" "$user"
}

echo "Benchmark: Josh vs Mesa (ai + manual)"
echo "Replicates per test run: $REPLICATES"
echo "Test runs per implementation: $ITERATIONS"
echo "Output file: $OUT_FILE"
echo

# Warm-up (untimed): builds the Josh .jshd preprocessing cache if missing and
# warms the JVM / Python / filesystem caches so the first timed run isn't an
# outlier.
echo "Warming up..."
"$JOSH_RUN" ai "$REPLICATES" true    >/dev/null 2>&1
"$JOSH_RUN" ai "$REPLICATES" false   >/dev/null 2>&1
"$JOSH_RUN" manual "$REPLICATES" true  >/dev/null 2>&1
"$JOSH_RUN" manual "$REPLICATES" false >/dev/null 2>&1
"$MESA_RUN" ai false "$REPLICATES"     >/dev/null 2>&1
"$MESA_RUN" ai true  "$REPLICATES"     >/dev/null 2>&1
"$MESA_RUN" manual false "$REPLICATES" >/dev/null 2>&1
"$MESA_RUN" manual true  "$REPLICATES" >/dev/null 2>&1

printf 'implementation,model,replicates,threaded,wallClockSeconds,userTimeSeconds\n' > "$OUT_FILE"

# Record one timed test: <impl> <model> <threaded> <run.sh> <args...>
record() {
  local impl="$1" model="$2" threaded="$3"; shift 3
  local out wall user
  out=$(time_run "$@")
  wall=${out%% *}; user=${out##* }
  printf '%s,%s,%s,%s,%s,%s\n' \
    "$impl" "$model" "$REPLICATES" "$threaded" "$wall" "$user" >> "$OUT_FILE"
  printf '  %-5s model=%-6s threaded=%-5s wall=%ss user=%ss\n' \
    "$impl" "$model" "$threaded" "$wall" "$user"
}

for i in $(seq 1 "$ITERATIONS"); do
  printf 'iter %2d/%d\n' "$i" "$ITERATIONS"
  # Rebuild Josh's .jshd preprocessing fresh before each timed Josh run, so the
  # measured time includes one preprocess pass. It is kept across the N
  # replicates inside a single run (never rebuilt between them); each Josh
  # config gets its own rebuild so their timings are comparable.
  rm -f "$SCRIPT_DIR"/reference/*.jshd
  record josh ai true  "$JOSH_RUN" ai "$REPLICATES" true
  rm -f "$SCRIPT_DIR"/reference/*.jshd
  record josh ai false "$JOSH_RUN" ai "$REPLICATES" false
  rm -f "$SCRIPT_DIR"/reference/*.jshd
  record josh manual true  "$JOSH_RUN" manual "$REPLICATES" true
  rm -f "$SCRIPT_DIR"/reference/*.jshd
  record josh manual false "$JOSH_RUN" manual "$REPLICATES" false
  record mesa ai false "$MESA_RUN" ai false "$REPLICATES"
  record mesa ai true  "$MESA_RUN" ai true  "$REPLICATES"
  record mesa manual false "$MESA_RUN" manual false "$REPLICATES"
  record mesa manual true  "$MESA_RUN" manual true  "$REPLICATES"
done

echo
echo "Wrote $OUT_FILE"
