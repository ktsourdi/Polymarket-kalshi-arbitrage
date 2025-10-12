from __future__ import annotations

import asyncio
from typing import List

from app.connectors.demo import fetch_kalshi_demo, fetch_polymarket_demo
from app.core.arb import detect_arbs
from app.core.executor import PaperExecutor
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


def cli():
    asyncio.run(run_once())


if __name__ == "__main__":
    cli()
