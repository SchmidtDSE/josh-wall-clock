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
# Usage: ./run_all.sh [replicates] [config]   (defaults: 100, all)
#   config = all | josh-serial | josh-threaded | mesa-serial | mesa-threaded
#   A single config lets a machine run just one of the four (fleet splits the
#   four configs across separate machines).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

REPLICATES="${1:-100}"
CONFIG="${2:-all}"
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

# Warm (untimed) one config so its timed run isn't a cold-cache outlier. Josh
# warm-ups also build the .jshd cache.
warm_config() {
  case "$1" in
    josh-serial|josh-threaded)
      rm -f "$SCRIPT_DIR"/reference/*.jshd
      "$JOSH_RUN" 1 true >/dev/null 2>&1 || true ;;
    mesa-serial)
      "$MESA_PY" "$MESA_SERIAL" 1 >/dev/null 2>&1 || true ;;
    mesa-threaded)
      PYTHON_GIL=0 "$MESA_FT_PY" "$MESA_THREADED" 1 "$CORES" >/dev/null 2>&1 || true ;;
  esac
}

# Time one config. Each Josh config rebuilds .jshd fresh so its preprocess pass
# is included in the timing and amortized across the replicates.
time_config() {
  case "$1" in
    josh-serial)
      rm -f "$SCRIPT_DIR"/reference/*.jshd
      record josh false "$JOSH_RUN" "$REPLICATES" false ;;
    josh-threaded)
      rm -f "$SCRIPT_DIR"/reference/*.jshd
      record josh true  "$JOSH_RUN" "$REPLICATES" true ;;
    mesa-serial)
      record mesa false "$MESA_PY" "$MESA_SERIAL" "$REPLICATES" ;;
    mesa-threaded)
      record mesa true  env PYTHON_GIL=0 "$MESA_FT_PY" "$MESA_THREADED" "$REPLICATES" "$CORES" ;;
  esac
}

case "$CONFIG" in
  all) CONFIGS=(josh-serial josh-threaded mesa-serial mesa-threaded) ;;
  josh-serial|josh-threaded|mesa-serial|mesa-threaded) CONFIGS=("$CONFIG") ;;
  *) echo "Unknown config: $CONFIG" >&2
     echo "  use: all | josh-serial | josh-threaded | mesa-serial | mesa-threaded" >&2
     exit 1 ;;
esac

echo "Warming up (${CONFIGS[*]})..."
for c in "${CONFIGS[@]}"; do warm_config "$c"; done

echo "Timing $REPLICATES replicates: ${CONFIGS[*]}"
for c in "${CONFIGS[@]}"; do time_config "$c"; done

echo
echo "Wrote $OUT"
cat "$OUT"
