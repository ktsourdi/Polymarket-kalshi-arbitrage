from __future__ import annotations

import asyncio
from typing import List

from app.connectors.demo import fetch_kalshi_demo, fetch_polymarket_demo
from app.core.arb import detect_arbs, detect_two_buy_arbs
from app.core.executor import LiveExecutor, PaperExecutor
from app.utils.logging import get_logger


logger = get_logger("main")


async def load_quotes():
    k, p = await asyncio.gather(fetch_kalshi_demo(), fetch_polymarket_demo())
    return k, p


async def run_once() -> int:
    kalshi_quotes, polymarket_quotes = await load_quotes()
    opps = detect_arbs(kalshi_quotes, polymarket_quotes)
    if not opps:
        logger.info("No opportunities found.")
        return 0

    logger.info("Found %d opportunities", len(opps))
    executor = PaperExecutor()
    executor.execute(opps)
    return len(opps)


async def run_live_once() -> int:
    # In live mode we still use demo fetchers for now; replace with real client fetchers
    kalshi_quotes, polymarket_quotes = await load_quotes()
    opps = detect_two_buy_arbs(kalshi_quotes, polymarket_quotes)
    if not opps:
        logger.info("No two-buy opportunities found.")
        return 0
    # Lazy import to avoid requiring httpx in non-live mode
    from app.connectors.kalshi import KalshiClient
    from app.connectors.polymarket import PolymarketClient

    kalshi = KalshiClient()
    poly = PolymarketClient()
    executor = LiveExecutor(kalshi, poly)
    await executor.execute_two_buy(opps)
    await kalshi.close()
    await poly.close()
    return len(opps)


def cli():
    import os
    live = os.environ.get("LIVE", "0") in {"1", "true", "TRUE", "yes"}
    if live:
        asyncio.run(run_live_once())
    else:
        asyncio.run(run_once())


if __name__ == "__main__":
    cli()
