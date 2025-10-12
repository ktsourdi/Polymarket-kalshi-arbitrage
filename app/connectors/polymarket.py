from __future__ import annotations

from typing import List

import httpx

from app.core.models import MarketQuote
from app.utils.logging import get_logger


logger = get_logger("polymarket")


class PolymarketClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = base_url or "https://clob.polymarket.com"
        self.api_key = api_key
        self._client = httpx.AsyncClient(timeout=10)

    async def close(self):
        await self._client.aclose()

    async def fetch_markets(self) -> List[dict]:
        # Placeholder for real API; returns empty list in this scaffold
        # Potential refs: https://docs.polymarket.com/
        return []

    async def fetch_quotes(self) -> List[MarketQuote]:
        markets = await self.fetch_markets()
        quotes: List[MarketQuote] = []
        for m in markets:
            event = m.get("question") or m.get("title") or ""
            yes_price = float(m.get("yes_price", 0)) / 1.0
            no_price = float(m.get("no_price", 0)) / 1.0
            size = float(m.get("liquidity", 0))
            quotes.append(
                MarketQuote(
                    exchange="polymarket",
                    market_id=str(m.get("id")),
                    event=event,
                    outcome="YES",
                    price=yes_price,
                    size=size,
                )
            )
            quotes.append(
                MarketQuote(
                    exchange="polymarket",
                    market_id=str(m.get("id")),
                    event=event,
                    outcome="NO",
                    price=no_price,
                    size=size,
                )
            )
        return quotes
