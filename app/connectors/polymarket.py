from __future__ import annotations

from typing import List
import os
import json
from datetime import datetime, timezone
import asyncio

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
        self._orderbook_url = os.environ.get("POLYMARKET_ORDERBOOK_URL", f"{self.base_url.rstrip('/')}/orderbook")

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
        markets: List[dict] = []

        async def paginate(url: str, base_params: dict) -> List[dict]:
            items: List[dict] = []
            offset = 0
            max_pages = int(os.environ.get("POLYMARKET_MAX_PAGES", "3"))
            for _ in range(max_pages):
                params = {"limit": int(os.environ.get("POLYMARKET_PAGE_LIMIT", "1000")), "offset": offset}
                params.update(base_params or {})
                batch = await _fetch(url, params=params)
                if not batch:
                    break
                items.extend(batch)
                if len(batch) < int(os.environ.get("POLYMARKET_PAGE_LIMIT", "1000")):
                    break
                offset += len(batch)
            return items

        # Try Gamma with active filter and sort by most recently updated
        gamma_markets = await paginate(
            self._markets_url,
            {"active": "true", "order": "updatedAt", "ascending": "false"},
        )
        if not gamma_markets:
            gamma_markets = await paginate(
                self._markets_url,
                {"order": "updatedAt", "ascending": "false"},
            )

        markets.extend(gamma_markets)

        # Fallback to CLOB markets if still nothing
        if not markets:
            clob_markets = await paginate(self._clob_markets_url, {})
            markets.extend(clob_markets)
        # Basic client-side filtering to avoid stale/historical markets
        def _is_live(m: dict) -> bool:
            # Treat missing fields as unknown/okay; only exclude explicit negatives
            if bool(m.get("archived")):
                return False
            if m.get("closed") is True:
                return False
            if m.get("active") is False:
                return False
            return True

        raw_count = len(markets)
        filtered = [m for m in markets if _is_live(m)]
        # If filtering nukes everything but we did receive data, return raw so we can inspect
        final = filtered if filtered or raw_count == 0 else markets
        # Date filter: keep reasonably current markets (past 30d to next 365d)
        def _parse_dt(value: str | None) -> datetime | None:
            if not value or not isinstance(value, str):
                return None
            try:
                if value.endswith("Z"):
                    value = value[:-1] + "+00:00"
                dt = datetime.fromisoformat(value)
                # Ensure timezone-aware (UTC) for all comparisons
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                return dt
            except Exception:
                return None

        now = datetime.now(timezone.utc)
        from datetime import timedelta
        past_cutoff = now - timedelta(days=30)
        future_cutoff = now + timedelta(days=365)

        timed: List[dict] = []
        include_no_date = os.environ.get("POLYMARKET_INCLUDE_NO_DATE", "0").lower() in {"1", "true", "yes"}
        for m in final:
            # Try multiple date sources for recency
            dt = (
                _parse_dt(m.get("endDateIso"))
                or _parse_dt(m.get("endDate"))
                or _parse_dt(m.get("updatedAt"))
                or _parse_dt(m.get("createdAt"))
            )
            if dt is None:
                # Look into first event if present
                evs = m.get("events") or []
                if isinstance(evs, list) and evs:
                    first = evs[0]
                    if isinstance(first, dict):
                        dt = _parse_dt(first.get("endDate")) or _parse_dt(first.get("updatedAt"))
            if dt is None:
                if include_no_date:
                    timed.append(m)
                continue
            if past_cutoff <= dt <= future_cutoff:
                timed.append(m)

        logger.info(
            "Polymarket markets fetched: raw=%d, post-filter=%d (returning=%d, date-window=%d)",
            raw_count,
            len(filtered),
            len(final),
            len(timed),
        )
        return timed

    async def fetch_quotes(self) -> List[MarketQuote]:
        markets = await self.fetch_markets()
        quotes: List[MarketQuote] = []
        tokens_needed: List[tuple[str, str, str]] = []  # (event, outcome, tokenId)
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
                    raw_outcome = str(name).strip()
                    outcome_name = raw_outcome.upper()
                    price = to_price(prices[idx])
                    token_id = None
                    if tokens and idx < len(tokens):
                        token_id = tokens[idx]
                    # Binary YES/NO market
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
                        if not token_id:
                            tokens_needed.append((event, outcome_name, token_id or ""))
                        mapped = True
                    # Categorical outcome: publish pseudo-binary "event — outcome" with YES price
                    elif price:
                        cat_event = f"{event} — {raw_outcome}"
                        quotes.append(
                            MarketQuote(
                                exchange="polymarket",
                                market_id=str(token_id or f"{m.get('id')}-{idx}"),
                                event=cat_event,
                                outcome="YES",
                                price=price,
                                size=size,
                            )
                        )
                        if not token_id:
                            tokens_needed.append((cat_event, "YES", token_id or ""))
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
            # Track tokens we still need from orderbook
            if tokens:
                if len(tokens) >= 1 and not yes_price:
                    tokens_needed.append((event, "YES", tokens[0]))
                if len(tokens) >= 2 and not no_price:
                    tokens_needed.append((event, "NO", tokens[1]))

        # Fetch missing prices via orderbook with bounded concurrency
        async def fetch_ob(token_id: str):
            try:
                resp = await self._client.get(self._orderbook_url, params={"tokenId": token_id})
                resp.raise_for_status()
                data = resp.json()
                ob = data.get("orderbook") or {}
                yes_arr = ob.get("yes_dollars") or ob.get("yes") or []
                no_arr = ob.get("no_dollars") or ob.get("no") or []
                def top(arr):
                    if not arr:
                        return None
                    first = arr[0]
                    if isinstance(first, list) and first:
                        return float(first[0])
                    try:
                        return float(first)
                    except Exception:
                        return None
                return top(yes_arr), top(no_arr)
            except Exception:
                return None

        sem = asyncio.Semaphore(int(os.environ.get("POLYMARKET_OB_CONCURRENCY", "8")))

        async def worker(ev: str, outcome: str, tok: str):
            if not tok:
                return None
            async with sem:
                res = await fetch_ob(tok)
                return (ev, outcome, tok, res)

        if tokens_needed:
            results = await asyncio.gather(*[worker(e, o, t) for e, o, t in tokens_needed], return_exceptions=True)
            for r in results:
                if not r or isinstance(r, Exception):
                    continue
                ev, outcome, tok, res = r
                if not res:
                    continue
                y, n = res
                price = y if outcome == "YES" else n
                if price:
                    quotes.append(
                        MarketQuote(
                            exchange="polymarket",
                            market_id=str(tok),
                            event=ev,
                            outcome=outcome,
                            price=float(price),
                            size=0.0,
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
