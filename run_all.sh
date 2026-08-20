#!/usr/bin/env bash
#
# Run all eight benchmark configurations once on this machine, at the given
# replicate count, and write one CSV row per configuration:
#
#   josh-ai                  (--serial-patches, forevertree.josh)
#   josh-ai-parallel         (parallel patches, forevertree.josh)
#   josh-manual              (--serial-patches, forevertree_manual.josh)
#   josh-manual-parallel     (parallel patches, forevertree_manual.josh)
#   mesa-ai                  (Python / forevertree.py)
#   mesa-ai-parallel         (Python 3.14t no-GIL, forevertree_threaded.py, nproc threads)
#   mesa-manual              (Python / forevertree_manual.py, serial)
#   mesa-manual-parallel     (Python / forevertree_manual.py, pathos ProcessPool)
#
# Output: results_<hostname>.csv with columns
#   hostname,implementation,model,threaded,replicates,cores,wallSeconds,userSeconds
#
# Josh's .jshd preprocessing is rebuilt fresh inside each timed Josh run (the
# .jshd is removed first), so each Josh timing includes one preprocess pass
# amortized across the REPLICATES. The Mesa references load the climate once
# per process and reuse it across replicates, so their climate setup is likewise
# paid once and amortized -- keeping the two sides symmetric. Each implementation
# also gets a cheap untimed warm-up so the timed run isn't a cold-cache outlier.
#
# Usage: ./run_all.sh [replicates] [config]   (defaults: 100, all)
#   config = all | josh-ai | josh-ai-parallel | josh-manual | josh-manual-parallel
#            | mesa-ai | mesa-ai-parallel | mesa-manual | mesa-manual-parallel
#   A single config lets a machine run just one of the eight (fleet splits the
#   eight configs across separate machines).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

REPLICATES="${1:-100}"
CONFIG="${2:-all}"
CORES="$(nproc)"
HOST="$(hostname)"
OUT="$SCRIPT_DIR/results_${HOST}.csv"

JOSH_RUN="$SCRIPT_DIR/reference/run.sh"
MESA_RUN="$SCRIPT_DIR/reference-mesa/run.sh"

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
  local impl="$1" model="$2" threaded="$3"; shift 3
  local out wall user
  out=$(time_run "$@")
  wall=${out%% *}; user=${out##* }
  printf '%s,%s,%s,%s,%s,%s,%s,%s\n' \
    "$HOST" "$impl" "$model" "$threaded" "$REPLICATES" "$CORES" "$wall" "$user" >> "$OUT"
  printf '  %-4s model=%-6s threaded=%-5s wall=%ss user=%ss\n' \
    "$impl" "$model" "$threaded" "$wall" "$user"
}

echo "Host=$HOST cores=$CORES replicates=$REPLICATES"
printf 'hostname,implementation,model,threaded,replicates,cores,wallSeconds,userSeconds\n' > "$OUT"

# Warm (untimed) one config so its timed run isn't a cold-cache outlier. Josh
# warm-ups also build the .jshd cache.
warm_config() {
  case "$1" in
    josh-ai|josh-ai-parallel)
      rm -f "$SCRIPT_DIR"/reference/*.jshd
      "$JOSH_RUN" ai 1 true >/dev/null 2>&1 || true ;;
    josh-manual|josh-manual-parallel)
      rm -f "$SCRIPT_DIR"/reference/*.jshd
      "$JOSH_RUN" manual 1 true >/dev/null 2>&1 || true ;;
    mesa-ai)
      "$MESA_RUN" ai false 1 >/dev/null 2>&1 || true ;;
    mesa-ai-parallel)
      "$MESA_RUN" ai true 1 "$CORES" >/dev/null 2>&1 || true ;;
    mesa-manual)
      "$MESA_RUN" manual false 1 >/dev/null 2>&1 || true ;;
    mesa-manual-parallel)
      "$MESA_RUN" manual true 1 >/dev/null 2>&1 || true ;;
  esac
}

# Time one config. Each Josh config rebuilds .jshd fresh so its preprocess pass
# is included in the timing and amortized across the replicates.
time_config() {
  case "$1" in
    josh-ai)
      rm -f "$SCRIPT_DIR"/reference/*.jshd
      record josh ai false "$JOSH_RUN" ai "$REPLICATES" false ;;
    josh-ai-parallel)
      rm -f "$SCRIPT_DIR"/reference/*.jshd
      record josh ai true  "$JOSH_RUN" ai "$REPLICATES" true ;;
    josh-manual)
      rm -f "$SCRIPT_DIR"/reference/*.jshd
      record josh manual false "$JOSH_RUN" manual "$REPLICATES" false ;;
    josh-manual-parallel)
      rm -f "$SCRIPT_DIR"/reference/*.jshd
      record josh manual true  "$JOSH_RUN" manual "$REPLICATES" true ;;
    mesa-ai)
      record mesa ai false "$MESA_RUN" ai false "$REPLICATES" ;;
    mesa-ai-parallel)
      record mesa ai true "$MESA_RUN" ai true "$REPLICATES" "$CORES" ;;
    mesa-manual)
      record mesa manual false "$MESA_RUN" manual false "$REPLICATES" ;;
    mesa-manual-parallel)
      record mesa manual true "$MESA_RUN" manual true "$REPLICATES" ;;
  esac
}

case "$CONFIG" in
  all)
    CONFIGS=(josh-ai josh-ai-parallel josh-manual josh-manual-parallel
             mesa-ai mesa-ai-parallel mesa-manual mesa-manual-parallel) ;;
  josh-ai|josh-ai-parallel|josh-manual|josh-manual-parallel|mesa-ai|mesa-ai-parallel|mesa-manual|mesa-manual-parallel)
    CONFIGS=("$CONFIG") ;;
  *) echo "Unknown config: $CONFIG" >&2
     echo "  use: all | josh-ai | josh-ai-parallel | josh-manual | josh-manual-parallel" >&2
     echo "       | mesa-ai | mesa-ai-parallel | mesa-manual | mesa-manual-parallel" >&2
     exit 1 ;;
esac

echo "Warming up (${CONFIGS[*]})..."
for c in "${CONFIGS[@]}"; do warm_config "$c"; done

echo "Timing $REPLICATES replicates: ${CONFIGS[*]}"
for c in "${CONFIGS[@]}"; do time_config "$c"; done

echo
echo "Wrote $OUT"
cat "$OUT"
