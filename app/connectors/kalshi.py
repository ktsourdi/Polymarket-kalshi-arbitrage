from __future__ import annotations

from typing import List
import os

import httpx

from app.core.models import MarketQuote
from app.utils.logging import get_logger


logger = get_logger("kalshi")


class KalshiClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, api_secret: str | None = None):
        self.base_url = base_url or "https://trading-api.kalshi.com/v2"
        self.api_key = api_key
        self.api_secret = api_secret
        self._client = httpx.AsyncClient(timeout=15)

    async def close(self):
        await self._client.aclose()

    async def fetch_markets(self) -> List[dict]:
        """Fetch markets from Kalshi public endpoints (read-only fallback).

        Note: Full authenticated flow requires signed headers. Here we first
        try public endpoints if available; otherwise return empty list.
        """
        try:
            url = os.environ.get("KALSHI_MARKETS_URL") or f"{self.base_url}/markets"
            resp = await self._client.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and "markets" in data:
                return list(data.get("markets") or [])
            if isinstance(data, list):
                return data
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to fetch Kalshi markets (public): %s", exc)
        return []

    async def fetch_quotes(self) -> List[MarketQuote]:
        markets = await self.fetch_markets()
        quotes: List[MarketQuote] = []
        for m in markets:
            event = m.get("title") or m.get("ticker") or ""
            yes_price = float(m.get("yes_price", 0)) / 100.0
            no_price = float(m.get("no_price", 0)) / 100.0
            size = float(m.get("liquidity", 0))
            quotes.append(
                MarketQuote(
                    exchange="kalshi",
                    market_id=str(m.get("id")),
                    event=event,
                    outcome="YES",
                    price=yes_price,
                    size=size,
                )
            )
            quotes.append(
                MarketQuote(
                    exchange="kalshi",
                    market_id=str(m.get("id")),
                    event=event,
                    outcome="NO",
                    price=no_price,
                    size=size,
                )
            )
        return quotes

    async def place_limit_order(
        self,
        market_id: str,
        outcome: str,
        side: str,
        price: float,
        size: float,
        tif: str = "GTC",
    ) -> dict:
        """Skeleton for placing a limit order on Kalshi.

        Notes:
        - Kalshi API requires auth headers and specific endpoints.
        - Price is typically in cents; convert as needed when implementing.
        - This function currently does nothing and returns a stub.
        """
        logger.info(
            "[DRY-RUN Kalshi] place %s %s %s @ %.2f size %.4f",
            side,
            outcome,
            market_id,
            price,
            size,
        )
        # TODO: implement real HTTP POST to Kalshi order endpoint
        return {"status": "stub", "id": None}
