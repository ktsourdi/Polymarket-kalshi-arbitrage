from __future__ import annotations

from typing import List
import os
import json

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
        # Primary public markets endpoint (Gamma API)
        self._markets_url = os.environ.get("POLYMARKET_MARKETS_URL", "https://gamma-api.polymarket.com/markets")
        # Fallback CLOB markets endpoint
        self._clob_markets_url = os.environ.get("POLYMARKET_CLOB_MARKETS_URL", f"{self.base_url.rstrip('/')}/markets")

    async def close(self):
        await self._client.aclose()

    async def fetch_markets(self) -> List[dict]:
        """Fetch active markets from Polymarket Gamma API (read-only).

        Falls back to an empty list on error. This does not require authentication.
        """
        async def _fetch(url: str, params: dict | None = None) -> List[dict]:
            try:
                resp = await self._client.get(url, params=params or {})
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, dict):
                    for key in ("markets", "data", "result"):
                        if key in data and isinstance(data[key], list):
                            return list(data[key])
                if isinstance(data, list):
                    return data
            except Exception as exc:  # noqa: BLE001
                logger.warning("Polymarket markets fetch failed at %s: %s", url, exc)
            return []

        # Try Gamma API first, then CLOB fallback
        markets = await _fetch(self._markets_url, params={"limit": 1000})
        if not markets:
            markets = await _fetch(self._clob_markets_url, params={"limit": 1000})
        return markets

    async def fetch_quotes(self) -> List[MarketQuote]:
        markets = await self.fetch_markets()
        quotes: List[MarketQuote] = []
        for m in markets:
            event = m.get("question") or m.get("title") or m.get("name") or ""
            size = float(m.get("liquidityNum") or m.get("liquidity") or 0)

            # Extract token ids
            token_field = m.get("clobTokenIds") or m.get("clob_token_ids") or m.get("tokenIds")
            tokens: List[str] = []
            if isinstance(token_field, list):
                tokens = [str(t) for t in token_field]
            elif isinstance(token_field, str):
                try:
                    maybe_list = json.loads(token_field)
                    if isinstance(maybe_list, list):
                        tokens = [str(t) for t in maybe_list]
                    else:
                        tokens = [s for s in token_field.replace("[", "").replace("]", "").split(",") if s.strip()]
                        tokens = [t.strip() for t in tokens]
                except Exception:
                    tokens = [s for s in token_field.replace("[", "").replace("]", "").split(",") if s.strip()]
                    tokens = [t.strip() for t in tokens]

            # Outcomes and prices arrays
            outcomes = m.get("shortOutcomes") or m.get("outcomes") or []
            if isinstance(outcomes, str):
                try:
                    outcomes = json.loads(outcomes)
                except Exception:
                    outcomes = [s.strip() for s in outcomes.split(",") if s.strip()]
            prices = m.get("outcomePrices") or []
            if isinstance(prices, str):
                try:
                    prices = json.loads(prices)
                except Exception:
                    prices = [s.strip() for s in prices.split(",") if s.strip()]

            def to_price(v) -> float:
                try:
                    p = float(v)
                except Exception:
                    return 0.0
                return p / 100.0 if p > 1.0 else p

            # If arrays align, map directly
            mapped = False
            if isinstance(outcomes, list) and outcomes and isinstance(prices, list) and len(prices) == len(outcomes):
                for idx, name in enumerate(outcomes):
                    outcome_name = str(name).upper()
                    price = to_price(prices[idx])
                    token_id = None
                    if tokens and idx < len(tokens):
                        token_id = tokens[idx]
                    if outcome_name in {"YES", "NO"} and price:
                        quotes.append(
                            MarketQuote(
                                exchange="polymarket",
                                market_id=str(token_id or f"{m.get('id')}-{outcome_name}"),
                                event=event,
                                outcome=outcome_name,
                                price=price,
                                size=size,
                            )
                        )
                        mapped = True

            if mapped:
                continue

            # Fallback: use bestAsk/bestBid if present for YES; derive NO from 1-yes if we must
            yes_price = m.get("bestAsk") or m.get("yesPrice") or None
            no_price = None
            if yes_price is not None:
                yes_price = to_price(yes_price)
            # Try to find an explicit NO price
            if isinstance(outcomes, list) and "NO" in [str(x).upper() for x in outcomes] and isinstance(prices, list):
                try:
                    idx_no = [str(x).upper() for x in outcomes].index("NO")
                    no_price = to_price(prices[idx_no])
                except Exception:
                    no_price = None

            if yes_price:
                token = tokens[0] if tokens else m.get("id")
                quotes.append(
                    MarketQuote(
                        exchange="polymarket",
                        market_id=str(token),
                        event=event,
                        outcome="YES",
                        price=yes_price,
                        size=size,
                    )
                )
            if no_price:
                token = tokens[1] if len(tokens) > 1 else m.get("id")
                quotes.append(
                    MarketQuote(
                        exchange="polymarket",
                        market_id=str(token),
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
