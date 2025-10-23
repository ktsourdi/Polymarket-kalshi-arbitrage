from __future__ import annotations

from typing import List, Optional
import os
from datetime import datetime, timezone

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
        markets: List[dict] = []
        try:
            url = os.environ.get("KALSHI_MARKETS_URL") or f"{self.base_url}/markets"
            headers = {}
            if self.bearer_token:
                headers["Authorization"] = f"Bearer {self.bearer_token}"
            cursor = None
            # Fetch more pages by default to improve coverage. Can override via env.
            max_pages = int(os.environ.get("KALSHI_MAX_PAGES", "10"))
            page = 0
            for _ in range(max_pages):  # soft cap to avoid huge downloads
                params = {"limit": int(os.environ.get("KALSHI_PAGE_LIMIT", "1000")), "status": "active"}
                if cursor:
                    params["cursor"] = cursor
                resp = await self._client.get(url, headers=headers, params=params, timeout=15)
                if resp.status_code == 401:
                    break
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, dict):
                    items = data.get("markets") or []
                    if items:
                        markets.extend(items)
                    cursor = data.get("cursor")
                    page += 1
                    if not cursor or page >= max_pages:
                        break
                elif isinstance(data, list):
                    markets.extend(data)
                    break
                else:
                    break
            if markets:
                return markets
            # Try public fallback (elections API) with pagination if available
            fallback = os.environ.get("KALSHI_FALLBACK_PUBLIC_URL") or "https://api.elections.kalshi.com/trade-api/v2/markets"
            cursor = None
            page = 0
            for _ in range(max_pages):
                # Elections API often rejects unknown params; do NOT pass status
                params = {"limit": int(os.environ.get("KALSHI_PAGE_LIMIT", "1000"))}
                if cursor:
                    params["cursor"] = cursor
                resp2 = await self._client.get(fallback, params=params, timeout=15)
                # If 400, retry once without params except cursor/limit adjustments
                if resp2.status_code == 400:
                    params = {"limit": int(os.environ.get("KALSHI_PAGE_LIMIT", "1000"))}
                    if cursor:
                        params["cursor"] = cursor
                    resp2 = await self._client.get(fallback, params=params, timeout=15)
                resp2.raise_for_status()
                data2 = resp2.json()
                if isinstance(data2, dict):
                    items = data2.get("markets") or []
                    if items:
                        markets.extend(items)
                    cursor = data2.get("cursor")
                    page += 1
                    if not cursor or page >= max_pages:
                        break
                elif isinstance(data2, list):
                    markets.extend(data2)
                    break
                else:
                    break
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to fetch Kalshi markets: %s", exc)
        return markets

    @staticmethod
    def _parse_dt(value: str | None) -> datetime | None:
        """Parse Kalshi date string."""
        if not value or not isinstance(value, str):
            return None
        try:
            # Kalshi uses ISO format dates
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except Exception:
            return None

    async def fetch_quotes(self) -> List[MarketQuote]:
        markets = await self.fetch_markets()
        quotes: List[MarketQuote] = []
        for m in markets:
            event = m.get("title") or m.get("subtitle") or m.get("ticker") or m.get("name") or ""
            
            # Extract end date from various possible fields
            end_date = (
                self._parse_dt(m.get("settle_time"))
                or self._parse_dt(m.get("settle_time_iso"))
                or self._parse_dt(m.get("end_time"))
                or self._parse_dt(m.get("expiration_time"))
                or self._parse_dt(m.get("expiration_time_iso"))
            )
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
                    end_date=end_date,
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
                    end_date=end_date,
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
