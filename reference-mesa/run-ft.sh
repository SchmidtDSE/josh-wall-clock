#!/usr/bin/env bash
#
# Launch the free-threaded (no-GIL) Mesa variant: forevertree_threaded.py on a
# free-threaded CPython build, with PYTHON_GIL=0 so the GIL stays disabled even
# after cftime (which has not declared free-thread safety) is imported.
#
# Usage: ./run-ft.sh [replicates] [threads]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPLICATES="${1:-1}"
THREADS="${2:-}"

# Prefer the free-threaded virtualenv (./.venv-ft); override with PYTHON=...
PYTHON="${PYTHON:-$SCRIPT_DIR/.venv-ft/bin/python}"
if [ ! -x "$PYTHON" ]; then
  echo "Free-threaded interpreter not found at $PYTHON" >&2
  echo "Create it with: uv venv --python 3.14t .venv-ft && \\" >&2
  echo "  VIRTUAL_ENV=.venv-ft uv pip install -r requirements.txt" >&2
  exit 1
fi

mkdir -p "$SCRIPT_DIR/output"

export PYTHON_GIL=0
exec "$PYTHON" "$SCRIPT_DIR/forevertree_threaded.py" "$REPLICATES" ${THREADS:+"$THREADS"}
