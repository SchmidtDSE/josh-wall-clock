#!/usr/bin/env bash
#
# Run all four benchmark configurations once on this machine, at the given
# replicate count, and write one CSV row per configuration:
#
#   josh single-thread   (--serial-patches)
#   josh multi-thread    (parallel patches, default)
#   mesa single-thread   (Python 3.12 / Decimal, forevertree.py)
#   mesa multi-thread    (Python 3.14t no-GIL, forevertree_threaded.py, nproc threads)
#
# Output: results_<hostname>.csv with columns
#   hostname,implementation,threaded,replicates,cores,wallSeconds,userSeconds
#
# Josh's .jshd preprocessing is rebuilt fresh inside each timed Josh run (the
# .jshd is removed first), so each Josh timing includes one preprocess pass
# amortized across the REPLICATES. The Mesa references load the climate once
# per process and reuse it across replicates, so their climate setup is likewise
# paid once and amortized -- keeping the two sides symmetric. Each implementation
# also gets a cheap untimed warm-up so the timed run isn't a cold-cache outlier.
#
# Usage: ./run_all.sh [replicates]   (default 100)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

REPLICATES="${1:-100}"
CORES="$(nproc)"
HOST="$(hostname)"
OUT="$SCRIPT_DIR/results_${HOST}.csv"

JOSH_RUN="$SCRIPT_DIR/reference/run.sh"
MESA_PY="$SCRIPT_DIR/reference-mesa/.venv/bin/python"
MESA_FT_PY="$SCRIPT_DIR/reference-mesa/.venv-ft/bin/python"
MESA_SERIAL="$SCRIPT_DIR/reference-mesa/forevertree.py"
MESA_THREADED="$SCRIPT_DIR/reference-mesa/forevertree_threaded.py"

# Time one invocation, echoing "<wallSeconds> <userSeconds>".
time_run() {
  local tf real user
  tf=$(mktemp)
  { TIMEFORMAT='%R %U'; time "$@" >/dev/null 2>&1; } 2>"$tf"
  read -r real user < "$tf"
  rm -f "$tf"
  printf '%s %s' "$real" "$user"
}

record() {
  local impl="$1" threaded="$2"; shift 2
  local out wall user
  out=$(time_run "$@")
  wall=${out%% *}; user=${out##* }
  printf '%s,%s,%s,%s,%s,%s,%s\n' \
    "$HOST" "$impl" "$threaded" "$REPLICATES" "$CORES" "$wall" "$user" >> "$OUT"
  printf '  %-4s threaded=%-5s wall=%ss user=%ss\n' "$impl" "$threaded" "$wall" "$user"
}

echo "Host=$HOST cores=$CORES replicates=$REPLICATES"
printf 'hostname,implementation,threaded,replicates,cores,wallSeconds,userSeconds\n' > "$OUT"

# --- Warm-ups (untimed) -----------------------------------------------------
echo "Warming up..."
# Build Josh's .jshd cache + warm JVM/FS; reused by both Josh timed runs.
rm -f "$SCRIPT_DIR"/reference/*.jshd
"$JOSH_RUN" 1 true >/dev/null 2>&1 || true
"$MESA_PY" "$MESA_SERIAL" 1 >/dev/null 2>&1 || true
PYTHON_GIL=0 "$MESA_FT_PY" "$MESA_THREADED" 1 "$CORES" >/dev/null 2>&1 || true

# --- Timed runs -------------------------------------------------------------
# Each Josh run rebuilds the .jshd fresh, so its preprocess pass is included in
# the timing and amortized across the replicates (one preprocess per config).
echo "Timing $REPLICATES replicates per config..."
rm -f "$SCRIPT_DIR"/reference/*.jshd
record josh false "$JOSH_RUN" "$REPLICATES" false
rm -f "$SCRIPT_DIR"/reference/*.jshd
record josh true  "$JOSH_RUN" "$REPLICATES" true
record mesa false "$MESA_PY" "$MESA_SERIAL" "$REPLICATES"
record mesa true  env PYTHON_GIL=0 "$MESA_FT_PY" "$MESA_THREADED" "$REPLICATES" "$CORES"

echo
echo "Wrote $OUT"
cat "$OUT"
