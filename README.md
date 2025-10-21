# Polymarket-kalshi-arbitrage

Automated cross-exchange arbitrage scaffolding for Kalshi and Polymarket.

## Quickstart

System python may be locked down. If virtualenv install fails, you can still run the demo (mocked connectors) directly with the system python:

```bash
python3 - << 'PY'
import asyncio
from app.main import run_once
asyncio.run(run_once())
PY
```

This demo uses mocked quotes to verify the pipeline: quote load -> arbitrage detection -> paper execution.

### Setup (recommended)

Create a virtual environment and install minimal deps:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If `pip` is not on PATH, use `python -m pip` instead of `pip`.

### Run live skeleton

Requires `httpx` to be installed (provided via `requirements.txt`). API calls are stubs; this only exercises the async order submission path.

```bash
LIVE=1 python3 - << 'PY'
import asyncio
from app.main import run_live_once
asyncio.run(run_live_once())
PY
```

If you encounter `ModuleNotFoundError: httpx`, ensure dependencies are installed as above.

## Project layout

- `app/main.py`: demo entrypoint
- `app/core/*`: models, matching, arbitrage, and paper executor
- `app/connectors/demo.py`: mocked market data for Kalshi and Polymarket
- `app/utils/*`: logging, text helpers
- `app/config/settings.py`: configuration models and defaults

## Next steps

### Live trading (auto-buy skeleton)

Set `LIVE=1` to trigger live mode. The current implementation wires a `LiveExecutor` that would place two buy orders (YES and NO across exchanges) when a sum-of-prices opportunity exists. The API calls are stubs; you must fill in auth and endpoints.

See "Run live skeleton" above.

Environment variables expected (to be finalized when wiring real APIs):

- `KALSHI_API_KEY`, `KALSHI_API_SECRET`, `KALSHI_BASE_URL`
- `POLYMARKET_API_KEY`, `POLYMARKET_BASE_URL`

### Roadmap

- Implement real Kalshi and Polymarket order/endpoints
- Robust event matching and explicit mapping
- Sizing with balances, fees, and slippage controls
- Live execution safeguards, retries, hedging, and reconciliation
