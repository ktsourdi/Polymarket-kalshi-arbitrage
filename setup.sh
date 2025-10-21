#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

python3 -m venv .venv || true
source .venv/bin/activate

python -m ensurepip --upgrade
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt

echo "\n✅ Setup complete. Activate with: source .venv/bin/activate"


