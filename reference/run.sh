#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
JAR="$SCRIPT_DIR/../joshsim-fat.jar"
OUTPUT_DIR="$SCRIPT_DIR/output"

mkdir -p "$OUTPUT_DIR"

cd "$SCRIPT_DIR"

if [ ! -f temperature.jshd ]; then
  java -XX:MaxRAMPercentage=90.0 -jar "$JAR" preprocess \
    forevertree.josh Main \
    ../data/maxtemp_synthetic.nc tasmax K \
    temperature.jshd \
    2>&1 | grep -vE "^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) |WARNING|INFO" || true
fi

if [ ! -f precipitation.jshd ]; then
  java -XX:MaxRAMPercentage=90.0 -jar "$JAR" preprocess \
    forevertree.josh Main \
    ../data/precip_synthetic.nc pr kgm2s \
    precipitation.jshd \
    2>&1 | grep -vE "^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) |WARNING|INFO" || true
fi

REPLICATES="${1:-1}"
THREADED="${2:-true}"   # true = parallel patches (default); false = --serial-patches

THREAD_FLAGS=()
if [ "$THREADED" != "true" ]; then
  THREAD_FLAGS+=(--serial-patches)
fi

java -XX:MaxRAMPercentage=90.0 -jar "$JAR" run \
  forevertree.josh Main \
  "--custom-tag=outputDir=$OUTPUT_DIR" \
  "--replicates=$REPLICATES" \
  "${THREAD_FLAGS[@]}" \
  --suppress-info
