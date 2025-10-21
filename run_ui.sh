#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate

python -m pip install -r requirements.txt >/dev/null 2>&1 || true

exec streamlit run app/ui/dashboard.py


