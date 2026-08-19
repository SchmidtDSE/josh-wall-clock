#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
JAR="$SCRIPT_DIR/../joshsim-fat.jar"
OUTPUT_DIR="$SCRIPT_DIR/output"

mkdir -p "$OUTPUT_DIR"

cd "$SCRIPT_DIR"

MODEL_ARG="${1:-}"
case "$MODEL_ARG" in
  manual)
    MODEL="forevertree_manual.josh"
    ;;
  ai)
    MODEL="forevertree.josh"
    ;;
  *)
    echo "Usage: $0 <manual|ai> [replicates] [threaded]" >&2
    echo "  manual  -> forevertree_manual.josh" >&2
    echo "  ai      -> forevertree.josh" >&2
    exit 1
    ;;
esac

if [ ! -f temperature.jshd ]; then
  java -XX:MaxRAMPercentage=90.0 -jar "$JAR" preprocess \
    "$MODEL" Main \
    ../data/maxtemp_synthetic.nc tasmax K \
    temperature.jshd \
    2>&1 | grep -vE "^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) |WARNING|INFO" || true
fi

if [ ! -f precipitation.jshd ]; then
  java -XX:MaxRAMPercentage=90.0 -jar "$JAR" preprocess \
    "$MODEL" Main \
    ../data/precip_synthetic.nc pr kgm2s \
    precipitation.jshd \
    2>&1 | grep -vE "^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) |WARNING|INFO" || true
fi

REPLICATES="${2:-1}"
THREADED="${3:-true}"   # true = parallel patches (default); false = --serial-patches

THREAD_FLAGS=()
if [ "$THREADED" != "true" ]; then
  THREAD_FLAGS+=(--serial-patches)
fi

java -XX:MaxRAMPercentage=90.0 -jar "$JAR" run \
  "$MODEL" Main \
  "--custom-tag=outputDir=$OUTPUT_DIR" \
  "--replicates=$REPLICATES" \
  --use-float-64 \
  "${THREAD_FLAGS[@]}" \
  --suppress-info
