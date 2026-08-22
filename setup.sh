#!/usr/bin/env bash
#
# Bootstrap an Ubuntu host to run the Josh-vs-Mesa benchmark.
#
# Run from the repo root after cloning, e.g.:
#   git clone https://github.com/<you>/josh-wall-profile.git
#   cd josh-wall-profile && bash setup.sh
#
# Installs: a JRE (for the Josh jar), uv (Python interpreter/venv manager), the
# Josh runtime jar, and the two Mesa virtualenvs:
#   reference-mesa/.venv     Python 3.12         -> serial Mesa (forevertree.py)
#   reference-mesa/.venv-ft  Python 3.14t no-GIL -> threaded Mesa (forevertree_threaded.py)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> Installing system packages (JRE, curl, unzip)"
sudo apt-get update -y
# Josh only needs a JRE to run the fat jar; 21 is the current LTS. If your
# Ubuntu release lacks openjdk-21, swap in openjdk-17-jre-headless.
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  openjdk-21-jre-headless curl unzip ca-certificates

echo "==> Installing uv (if missing)"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

echo "==> Fetching Josh runtime jar (if missing)"
JAR="$SCRIPT_DIR/joshsim-fat.jar"
if [ ! -f "$JAR" ]; then
  curl -fSL "https://www.joshsim.org/dist/freeze/josh-wall-clock-snapshot-202608.jar" -o "$JAR"
fi

echo "==> Creating Mesa serial venv (Python 3.12)"
cd "$SCRIPT_DIR/reference-mesa"
uv venv --python 3.12 .venv
VIRTUAL_ENV=.venv uv pip install -r requirements.txt

echo "==> Creating Mesa free-threaded venv (Python 3.14t)"
uv venv --python 3.14t .venv-ft
VIRTUAL_ENV=.venv-ft uv pip install -r requirements.txt

echo "==> Sanity checks"
java -version
./.venv/bin/python -c "import mesa; print('mesa serial OK', mesa.__version__)"
PYTHON_GIL=0 ./.venv-ft/bin/python -c "import sys, mesa; print('mesa free-threaded OK', mesa.__version__)"

echo "==> Setup complete."
