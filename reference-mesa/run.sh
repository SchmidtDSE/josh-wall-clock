#!/usr/bin/env bash
#
# Launch a Mesa ForeverTree variant by (model, threaded) selection.
#
#   ./run.sh <model> <threaded> [replicates] [threads] [output]
#
#     model    ai | manual          (ai = AI-generated reference; manual = hand-written)
#     threaded true | false         (parallel vs serial)
#
# The GIL-free build is only used for the AI threaded config, which runs the
# per-step patch loop across a free-threaded CPython 3.14t (no-GIL) interpreter
# with PYTHON_GIL=0 so threads actually parallelize:
#
#   ai + true     -> forevertree_threaded.py on ./.venv-ft  (no-GIL, nproc threads)
#   ai + false    -> forevertree.py          on ./.venv     (serial, GIL-enabled)
#   manual + true -> forevertree_manual.py   on ./.venv     (pathos ProcessPool)
#   manual + false-> forevertree_manual.py   on ./.venv     (serial)
#
# The manual variant already takes a threaded flag itself, so it is passed
# through; the pathos ProcessPool works on a normal GIL-enabled CPython because
# it uses separate processes, so no GIL-free interpreter is needed for it.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

MODEL="${1:?usage: run.sh <ai|manual> <threaded:true|false> [replicates] [threads] [output]}"
THREADED="${2:?usage: run.sh <ai|manual> <threaded:true|false> [replicates] [threads] [output]}"
REPLICATES="${3:-1}"
THREADS="${4:-}"
OUTPUT="${5:-}"

# Prefer a local virtualenv; override explicitly with PYTHON=/path/to/python.
PYTHON="${PYTHON:-$SCRIPT_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
  PYTHON="${SCRIPT_DIR}/venv/bin/python"
fi
if [ ! -x "$PYTHON" ]; then
  PYTHON="$(command -v python3 || command -v python)"
fi

mkdir -p "$SCRIPT_DIR/output"

case "$MODEL:$THREADED" in
  ai:true)
    FT_PYTHON="${PYTHON_FT:-$SCRIPT_DIR/.venv-ft/bin/python}"
    if [ ! -x "$FT_PYTHON" ]; then
      echo "Free-threaded interpreter not found at $FT_PYTHON" >&2
      echo "Create it with: uv venv --python 3.14t .venv-ft && \\" >&2
      echo "  VIRTUAL_ENV=.venv-ft uv pip install -r requirements.txt" >&2
      exit 1
    fi
    export PYTHON_GIL=0
    exec "$FT_PYTHON" "$SCRIPT_DIR/forevertree_threaded.py" \
      "$REPLICATES" ${THREADS:+"$THREADS"}
    ;;
  ai:false)
    exec "$PYTHON" "$SCRIPT_DIR/forevertree.py" "$REPLICATES"
    ;;
  manual:true|manual:false)
    out_dir="${OUTPUT:-$SCRIPT_DIR/output}"
    mkdir -p "$out_dir"
    if [ "$THREADED" = "true" ]; then
      template="$out_dir/results_manual_%d_parallel.csv"
    else
      template="$out_dir/results_manual_%d.csv"
    fi
    exec "$PYTHON" "$SCRIPT_DIR/forevertree_manual.py" \
      "$REPLICATES" "$THREADED" "$template"
    ;;
  *)
    echo "Unknown model/threaded combo: $MODEL / $THREADED" >&2
    echo "  model = ai | manual ; threaded = true | false" >&2
    exit 1
    ;;
esac
