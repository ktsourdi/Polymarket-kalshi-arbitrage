from __future__ import annotations

from typing import List, Optional
import os

import httpx

from app.core.models import MarketQuote
from app.utils.logging import get_logger


logger = get_logger("kalshi")


class KalshiClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        bearer_token: Optional[str] | None = None,
    ):
        self.base_url = base_url or "https://trading-api.kalshi.com/v2"
        self.api_key = api_key
        self.api_secret = api_secret
        self.bearer_token = bearer_token or os.environ.get("KALSHI_BEARER") or os.environ.get("KALSHI_SESSION_TOKEN")
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
            headers = {}
            if self.bearer_token:
                headers["Authorization"] = f"Bearer {self.bearer_token}"
            resp = await self._client.get(url, headers=headers, timeout=15)
            if resp.status_code == 401:
                # Try public elections endpoint as a fallback
                fallback = os.environ.get("KALSHI_FALLBACK_PUBLIC_URL") or "https://api.elections.kalshi.com/trade-api/v2/markets"
                try:
                    resp2 = await self._client.get(fallback, timeout=15)
                    resp2.raise_for_status()
                    data2 = resp2.json()
                    if isinstance(data2, dict) and "markets" in data2:
                        return list(data2.get("markets") or [])
                    if isinstance(data2, list):
                        return data2
                except Exception as exc2:  # noqa: BLE001
                    logger.warning("Kalshi fallback public markets failed: %s", exc2)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and "markets" in data:
                return list(data.get("markets") or [])
            if isinstance(data, list):
                return data
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to fetch Kalshi markets: %s", exc)
        return []

    async def fetch_quotes(self) -> List[MarketQuote]:
        markets = await self.fetch_markets()
        quotes: List[MarketQuote] = []
        for m in markets:
            event = m.get("title") or m.get("subtitle") or m.get("ticker") or m.get("name") or ""
            # Prefer dollar fields (already 0-1). Fallback to integer cents.
            def _to_price_dollars(*keys):
                for k in keys:
                    val = m.get(k)
                    if val is None:
                        continue
                    try:
                        return float(val)
                    except Exception:
                        try:
                            return float(str(val))
                        except Exception:
                            continue
                return 0.0

            def _to_price_cents(*keys):
                for k in keys:
                    val = m.get(k)
                    if val is None:
                        continue
                    try:
                        return float(val) / 100.0
                    except Exception:
                        continue
                return 0.0

            # Buy prices (best asks)
            yes_price = _to_price_dollars("yes_ask_dollars", "yesAskDollars")
            no_price = _to_price_dollars("no_ask_dollars", "noAskDollars")
            if not yes_price:
                yes_price = _to_price_cents("yes_ask", "yesAsk")
            if not no_price:
                no_price = _to_price_cents("no_ask", "noAsk")

            size = float(m.get("liquidity", 0) or m.get("open_interest", 0) or 0)
            quotes.append(
                MarketQuote(
                    exchange="kalshi",
                    market_id=str(m.get("id") or m.get("market_id") or m.get("ticker")),
                    event=event,
                    outcome="YES",
                    price=yes_price,
                    size=size,
                )
            )
            quotes.append(
                MarketQuote(
                    exchange="kalshi",
                    market_id=str(m.get("id") or m.get("market_id") or m.get("ticker")),
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
