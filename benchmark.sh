#!/usr/bin/env bash
#
# Wall-clock + user-CPU benchmark: Josh (BigDecimal) vs Mesa (Decimal).
#
# Each "test" runs one implementation with a given number of replicates, all
# inside a single process (one JVM for Josh, one Python interpreter for Mesa).
# This script runs that test ITERATIONS times per configuration, measuring
# each test's wall-clock and user-CPU time, and appends one row per test to a
# CSV with columns:
#   implementation,replicates,threaded,wallClockSeconds,userTimeSeconds
#
# Three configurations are timed each iteration:
#   josh threaded=true   (default: patches run in parallel)
#   josh threaded=false  (--serial-patches)
#   mesa threaded=false  (Python/Decimal is single-threaded)
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
JAR_URL="https://www.joshsim.org/dist/dev/joshsim-fat.jar"

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

echo "Benchmark: Josh (BigDecimal) vs Mesa (Decimal)"
echo "Replicates per test run: $REPLICATES"
echo "Test runs per implementation: $ITERATIONS"
echo "Output file: $OUT_FILE"
echo

# Warm-up (untimed): builds the Josh .jshd preprocessing cache if missing and
# warms the JVM / Python / filesystem caches so the first timed run isn't an
# outlier.
echo "Warming up..."
"$JOSH_RUN" "$REPLICATES" true  >/dev/null 2>&1
"$JOSH_RUN" "$REPLICATES" false >/dev/null 2>&1
"$MESA_RUN" "$REPLICATES"       >/dev/null 2>&1

printf 'implementation,replicates,threaded,wallClockSeconds,userTimeSeconds\n' > "$OUT_FILE"

# Record one timed test: <impl> <threaded> <run.sh> <args...>
record() {
  local impl="$1" threaded="$2"; shift 2
  local out wall user
  out=$(time_run "$@")
  wall=${out%% *}; user=${out##* }
  printf '%s,%s,%s,%s,%s\n' "$impl" "$REPLICATES" "$threaded" "$wall" "$user" >> "$OUT_FILE"
  printf '  %-5s threaded=%-5s wall=%ss user=%ss\n' "$impl" "$threaded" "$wall" "$user"
}

for i in $(seq 1 "$ITERATIONS"); do
  printf 'iter %2d/%d\n' "$i" "$ITERATIONS"
  # Rebuild Josh's .jshd preprocessing fresh before each timed Josh run, so the
  # measured time includes one preprocess pass. It is kept across the N
  # replicates inside a single run (never rebuilt between them); each of the two
  # Josh configs gets its own rebuild so their timings are comparable.
  rm -f "$SCRIPT_DIR"/reference/*.jshd
  record josh true  "$JOSH_RUN" "$REPLICATES" true
  rm -f "$SCRIPT_DIR"/reference/*.jshd
  record josh false "$JOSH_RUN" "$REPLICATES" false
  record mesa false "$MESA_RUN" "$REPLICATES"
done

echo
echo "Wrote $OUT_FILE"
