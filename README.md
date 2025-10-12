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

## Project layout

- `app/main.py`: demo entrypoint
- `app/core/*`: models, matching, arbitrage, and paper executor
- `app/connectors/demo.py`: mocked market data for Kalshi and Polymarket
- `app/utils/*`: logging, text helpers
- `app/config/settings.py`: configuration models and defaults

## Next steps

- Add real Kalshi and Polymarket APIs and authentication
- Implement robust event matching and explicit mapping
- Add sizing with balances, fees, and slippage controls
- Implement live execution and risk checks
