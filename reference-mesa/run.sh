#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPLICATES="${1:-1}"

# Prefer a local virtualenv (./.venv) if present; otherwise fall back to the
# system interpreter. Override explicitly with PYTHON=/path/to/python.
PYTHON="${PYTHON:-$SCRIPT_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
  PYTHON="$(command -v python3 || command -v python)"
fi

mkdir -p "$SCRIPT_DIR/output"

# One process produces all replicates (results_0.csv .. results_{N-1}.csv).
exec "$PYTHON" "$SCRIPT_DIR/forevertree.py" "$REPLICATES"
