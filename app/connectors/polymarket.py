from __future__ import annotations

from typing import List
import os

import httpx

from app.core.models import MarketQuote
from app.utils.logging import get_logger


logger = get_logger("polymarket")


class PolymarketClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        # CLOB base url (for orders); for read-only markets we use the Gamma API
        self.base_url = base_url or "https://clob.polymarket.com"
        self.api_key = api_key
        self._client = httpx.AsyncClient(timeout=15)
        # Public markets endpoint (read-only)
        self._markets_url = os.environ.get("POLYMARKET_MARKETS_URL", "https://gamma-api.polymarket.com/markets")

    async def close(self):
        await self._client.aclose()

    async def fetch_markets(self) -> List[dict]:
        """Fetch active markets from Polymarket Gamma API (read-only).

        Falls back to an empty list on error. This does not require authentication.
        """
        try:
            resp = await self._client.get(self._markets_url, params={"active": "true"})
            resp.raise_for_status()
            data = resp.json()
            # Some deployments return an object with a "markets" key, others a list
            if isinstance(data, dict) and "markets" in data:
                return list(data.get("markets") or [])
            if isinstance(data, list):
                return data
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to fetch Polymarket markets: %s", exc)
        return []

    async def fetch_quotes(self) -> List[MarketQuote]:
        markets = await self.fetch_markets()
        quotes: List[MarketQuote] = []
        for m in markets:
            event = m.get("question") or m.get("title") or m.get("name") or ""
            # Market may have per-outcome token info; try to extract prices and IDs
            yes_price = None
            no_price = None
            yes_token = None
            no_token = None
            size = float(m.get("liquidity", 0) or 0)

            # Common shapes seen in Gamma API payloads
            outcomes = m.get("outcomes") or m.get("contracts") or []
            if isinstance(outcomes, list) and outcomes:
                for o in outcomes:
                    o_name = (o.get("name") or o.get("outcome") or "").upper()
                    token_id = o.get("tokenId") or o.get("token_id") or o.get("id")
                    # Prefer best ask as a proxy for price to buy
                    best_ask = o.get("bestAsk") or o.get("best_ask")
                    last_price = o.get("lastPrice") or o.get("last_price")
                    price = best_ask if best_ask is not None else last_price
                    if price is not None:
                        price = float(price)
                    if o_name == "YES":
                        yes_price = price
                        yes_token = token_id
                    elif o_name == "NO":
                        no_price = price
                        no_token = token_id

            # Some payloads may include direct fields
            yes_price = float(m.get("yes_price", yes_price or 0) or 0)
            no_price = float(m.get("no_price", no_price or 0) or 0)
            yes_token = yes_token or m.get("yesTokenId") or m.get("yes_token_id") or m.get("id")
            no_token = no_token or m.get("noTokenId") or m.get("no_token_id") or m.get("id")

            if yes_price:
                quotes.append(
                    MarketQuote(
                        exchange="polymarket",
                        market_id=str(yes_token),
                        event=event,
                        outcome="YES",
                        price=yes_price,
                        size=size,
                    )
                )
            if no_price:
                quotes.append(
                    MarketQuote(
                        exchange="polymarket",
                        market_id=str(no_token),
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
        """Skeleton for placing a limit order on Polymarket.

        Notes:
        - Polymarket uses CLOB; requires API key and signature.
        - This function currently does nothing and returns a stub.
        """
        logger.info(
            "[DRY-RUN Polymarket] place %s %s %s @ %.2f size %.4f",
            side,
            outcome,
            market_id,
            price,
            size,
        )
        # TODO: implement real HTTP request to Polymarket order endpoint
        return {"status": "stub", "id": None}
