from __future__ import annotations

import random
from typing import List

from app.core.models import MarketQuote


EVENTS = [
    ("US CPI YoY Oct 2025 >= 3.0?", ["YES", "NO"]),
    ("Will Fed cut rates in Dec 2025?", ["YES", "NO"]),
    ("BTC to close > $100k in 2025?", ["YES", "NO"]),
]


def _clip_price(p: float) -> float:
    return max(0.01, min(0.99, p))


async def _generate_quotes(exchange: str) -> List[MarketQuote]:
    quotes: List[MarketQuote] = []
    for idx, (event, outcomes) in enumerate(EVENTS):
        base = random.uniform(0.2, 0.8)
        skew = random.uniform(-0.05, 0.05)
        yes_price = _clip_price(base + skew)
        no_price = _clip_price(1 - yes_price)
        size = random.uniform(50, 300)
        quotes.append(
            MarketQuote(
                exchange=exchange,
                market_id=f"{exchange}-{idx}-YES",
                event=event,
                outcome="YES",
                price=yes_price,
                size=size,
            )
        )
        quotes.append(
            MarketQuote(
                exchange=exchange,
                market_id=f"{exchange}-{idx}-NO",
                event=event,
                outcome="NO",
                price=no_price,
                size=size,
            )
        )
    return quotes


async def fetch_kalshi_demo() -> List[MarketQuote]:
    return await _generate_quotes("kalshi")


async def fetch_polymarket_demo() -> List[MarketQuote]:
    return await _generate_quotes("polymarket")
