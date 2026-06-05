#!/usr/bin/env bash
#
# Fast CI smoke check: run ONE benchmark config end-to-end at a tiny scale
# (default 2 replicates, a single timestep) just to prove it executes and writes
# output. This is NOT a timing benchmark -- it leaves the reference models
# untouched and only shrinks the workload:
#
#   * Mesa configs delegate to ci/quick_mesa.py, which overrides NUM_STEPS to 1.
#   * Josh configs run reference/run.sh against a temporary 1-step copy of
#     forevertree.josh (Josh has no CLI step limit), restoring the original on
#     exit.
#
# Missing tooling is provisioned on demand: the Josh jar is downloaded if
# absent, and each Mesa venv is created with uv if absent (mirroring setup.sh),
# so this works both in CI and on a fresh local checkout.
#
# Usage: ci/quick_check.sh <config> [replicates]
#   config = josh-serial | josh-threaded | mesa-serial | mesa-threaded
set -euo pipefail

CONFIG="${1:?usage: quick_check.sh <config> [replicates]}"
REPLICATES="${2:-2}"

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

JAR="$REPO_DIR/joshsim-fat.jar"
JAR_URL="https://www.joshsim.org/dist/dev/joshsim-fat.jar"
MESA_DIR="$REPO_DIR/reference-mesa"

# Restore the (temporarily shrunk) Josh model on exit. Globals, so the EXIT
# trap can see them after run_josh returns.
JOSH_SRC=""
JOSH_BACKUP=""
restore_josh() {
  if [ -n "$JOSH_BACKUP" ] && [ -f "$JOSH_BACKUP" ]; then
    mv -f "$JOSH_BACKUP" "$JOSH_SRC"
  fi
  JOSH_BACKUP=""
}
trap restore_josh EXIT

ensure_jar() {
  if [ ! -f "$JAR" ]; then
    echo "==> Fetching Josh runtime jar"
    curl -fSL "$JAR_URL" -o "$JAR"
  fi
}

ensure_venv() {  # <venv-dir> <python-spec>
  local dir="$1" pyspec="$2"
  if [ ! -x "$dir/bin/python" ]; then
    echo "==> Creating venv $dir ($pyspec)"
    uv venv --python "$pyspec" "$dir"
    VIRTUAL_ENV="$dir" uv pip install -r "$MESA_DIR/requirements.txt"
  fi
}

run_josh() {  # <threaded: true|false>
  local threaded="$1"
  ensure_jar
  JOSH_SRC="$REPO_DIR/reference/forevertree.josh"
  JOSH_BACKUP="$(mktemp)"
  cp "$JOSH_SRC" "$JOSH_BACKUP"
  # Single timestep: keep steps.low at 0 and pull steps.high down to 0.
  sed -i 's/^\( *steps\.high *= *\)[0-9][0-9]*\( *count\)/\10\2/' "$JOSH_SRC"
  rm -f "$REPO_DIR"/reference/*.jshd
  "$REPO_DIR/reference/run.sh" "$REPLICATES" "$threaded"
}

case "$CONFIG" in
  josh-serial)   run_josh false ;;
  josh-threaded) run_josh true ;;
  mesa-serial)
    ensure_venv "$MESA_DIR/.venv" 3.12
    "$MESA_DIR/.venv/bin/python" "$REPO_DIR/ci/quick_mesa.py" serial "$REPLICATES" ;;
  mesa-threaded)
    ensure_venv "$MESA_DIR/.venv-ft" 3.14t
    PYTHON_GIL=0 "$MESA_DIR/.venv-ft/bin/python" \
      "$REPO_DIR/ci/quick_mesa.py" threaded "$REPLICATES" "$(nproc)" ;;
  *)
    echo "Unknown config: $CONFIG" >&2
    echo "  use: josh-serial | josh-threaded | mesa-serial | mesa-threaded" >&2
    exit 1 ;;
esac

echo "==> Verifying output"
shopt -s nullglob
case "$CONFIG" in
  josh-*)        outputs=("$REPO_DIR"/reference/output/results_*.csv) ;;
  mesa-serial)   outputs=("$MESA_DIR"/output/results_*.csv) ;;
  mesa-threaded) outputs=("$MESA_DIR"/output/results_threaded_*.csv) ;;
esac

if [ ${#outputs[@]} -eq 0 ]; then
  echo "FAIL: $CONFIG produced no output CSV" >&2
  exit 1
fi

echo "OK: $CONFIG wrote ${#outputs[@]} CSV(s); first rows of ${outputs[0]##*/}:"
head -n 3 "${outputs[0]}"
