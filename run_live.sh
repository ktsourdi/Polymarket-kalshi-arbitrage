#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate

LIVE=1 python - << 'PY'
import asyncio
from app.main import run_live_once
asyncio.run(run_live_once())
PY


