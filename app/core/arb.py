"""Arbitrage detection algorithms.

This module contains the core logic for detecting arbitrage opportunities
across exchanges. It includes:
- Cross-exchange arbitrage detection (buy YES on one exchange, buy NO on the other)
- Two-buy arbitrage detection (sum of prices < 1.0)
- Edge calculation accounting for fees and slippage
"""

from __future__ import annotations

from typing import Iterable, List

from app.config.settings import settings
from app.core.models import CrossExchangeArb, MarketQuote, TwoBuyArb


def compute_edge_bps(long_price: float, short_price: float) -> float:
    implied_total = long_price + (1.0 - short_price)
    edge = 1.0 - implied_total
    return edge * 10000.0


def detect_arbs(
    kalshi_quotes: Iterable[MarketQuote], polymarket_quotes: Iterable[MarketQuote]
) -> List[CrossExchangeArb]:
    # Index by event -> outcome quotes
    from collections import defaultdict

    k_by_event: dict[str, dict[str, MarketQuote]] = defaultdict(dict)
    p_by_event: dict[str, dict[str, MarketQuote]] = defaultdict(dict)
    def key(e: str) -> str:
        return e.lower().strip()

    for q in kalshi_quotes:
        k_by_event[key(q.event)][q.outcome] = q
    for q in polymarket_quotes:
        p_by_event[key(q.event)][q.outcome] = q

    arbs: List[CrossExchangeArb] = []
    for event_key in set(k_by_event.keys()) & set(p_by_event.keys()):
        k = k_by_event[event_key]
        p = p_by_event[event_key]
        if "YES" in k and "NO" in p:
            # Account for fees and slippage buffers on both legs
            total_bps = settings.fees.taker_bps + settings.risk.slippage_bps
            edge_bps = compute_edge_bps(k["YES"].price, p["NO"].price) - total_bps
            if edge_bps > 0:
                max_notional = min(k["YES"].size * k["YES"].price, p["NO"].size * (1 - p["NO"].price), settings.risk.max_notional_per_leg)
                gross_profit = edge_bps / 10000.0 * max_notional
                if gross_profit >= settings.risk.min_profit_usd:
                    arbs.append(
                        CrossExchangeArb(
                            event_key=event_key,
                            long=k["YES"],
                            short=p["NO"],
                            edge_bps=edge_bps,
                            gross_profit_usd=gross_profit,
                            max_notional=max_notional,
                        )
                    )
        if "YES" in p and "NO" in k:
            edge_bps = compute_edge_bps(p["YES"].price, k["NO"].price) - total_bps
            if edge_bps > 0:
                max_notional = min(p["YES"].size * p["YES"].price, k["NO"].size * (1 - k["NO"].price), settings.risk.max_notional_per_leg)
                gross_profit = edge_bps / 10000.0 * max_notional
                if gross_profit >= settings.risk.min_profit_usd:
                    arbs.append(
                        CrossExchangeArb(
                            event_key=event_key,
                            long=p["YES"],
                            short=k["NO"],
                            edge_bps=edge_bps,
                            gross_profit_usd=gross_profit,
                            max_notional=max_notional,
                        )
                    )

    return arbs


def detect_two_buy_arbs(
    kalshi_quotes: Iterable[MarketQuote], polymarket_quotes: Iterable[MarketQuote]
) -> List[TwoBuyArb]:
    from collections import defaultdict

    k_by_event: dict[str, dict[str, MarketQuote]] = defaultdict(dict)
    p_by_event: dict[str, dict[str, MarketQuote]] = defaultdict(dict)
    for q in kalshi_quotes:
        k_by_event[q.event][q.outcome] = q
    for q in polymarket_quotes:
        p_by_event[q.event][q.outcome] = q

    results: List[TwoBuyArb] = []
    taker_fee = settings.fees.taker_bps / 10000.0
    slip_fee = settings.risk.slippage_bps / 10000.0
    for event in set(k_by_event.keys()) & set(p_by_event.keys()):
        k = k_by_event[event]
        p = p_by_event[event]
        # Case A: buy YES on Kalshi, buy NO on Polymarket
        if "YES" in k and "NO" in p:
            sum_price = k["YES"].price + p["NO"].price
            # Fees scale with notional, so subtract fee on each leg proportional to price
            edge = 1.0 - sum_price - (taker_fee + slip_fee) * (k["YES"].price + p["NO"].price)
            if edge > 0:
                # Cap by available size and per-leg notional limits (convert $ cap to contracts)
                cap_yes = settings.risk.max_notional_per_leg / max(k["YES"].price, 1e-9)
                cap_no = settings.risk.max_notional_per_leg / max(p["NO"].price, 1e-9)
                contracts = min(k["YES"].size, p["NO"].size, cap_yes, cap_no)
                gross_profit = edge * contracts
                results.append(
                    TwoBuyArb(
                        event_key=event,
                        buy_yes=k["YES"],
                        buy_no=p["NO"],
                        sum_price=sum_price,
                        edge_bps=edge * 10000.0,
                        contracts=contracts,
                        gross_profit_usd=gross_profit,
                    )
                )
        # Case B: buy YES on Polymarket, buy NO on Kalshi
        if "YES" in p and "NO" in k:
            sum_price = p["YES"].price + k["NO"].price
            edge = 1.0 - sum_price - (taker_fee + slip_fee) * (p["YES"].price + k["NO"].price)
            if edge > 0:
                cap_yes = settings.risk.max_notional_per_leg / max(p["YES"].price, 1e-9)
                cap_no = settings.risk.max_notional_per_leg / max(k["NO"].price, 1e-9)
                contracts = min(p["YES"].size, k["NO"].size, cap_yes, cap_no)
                gross_profit = edge * contracts
                results.append(
                    TwoBuyArb(
                        event_key=event,
                        buy_yes=p["YES"],
                        buy_no=k["NO"],
                        sum_price=sum_price,
                        edge_bps=edge * 10000.0,
                        contracts=contracts,
                        gross_profit_usd=gross_profit,
                    )
                )

    # Filter by min profit
    results = [r for r in results if r.gross_profit_usd >= settings.risk.min_profit_usd]
    return results


def detect_arbs_with_matcher(
    kalshi_quotes: Iterable[MarketQuote],
    polymarket_quotes: Iterable[MarketQuote],
    similarity_threshold: float = 0.78,
    explicit_map: dict[str, str] | None = None,
) -> List[CrossExchangeArb]:
    """Detect cross-exchange arbs using fuzzy event matching.

    This pairs events by text similarity (via `EventMatcher`) and then applies the
    same pricing logic as `detect_arbs`.
    """
    from collections import defaultdict
    from app.core.matching import EventMatcher

    # Index quotes by event and outcome for both exchanges
    def key_event(e: str) -> str:
        return e.lower().strip()

    k_by_event: dict[str, dict[str, MarketQuote]] = defaultdict(dict)
    p_by_event: dict[str, dict[str, MarketQuote]] = defaultdict(dict)
    unique_k_events: set[str] = set()
    unique_p_events: set[str] = set()
    for q in kalshi_quotes:
        k_by_event[key_event(q.event)][q.outcome] = q
        unique_k_events.add(q.event)
    for q in polymarket_quotes:
        p_by_event[key_event(q.event)][q.outcome] = q
        unique_p_events.add(q.event)

    # Build fuzzy mapping from Kalshi -> best Polymarket event
    matcher = EventMatcher(explicit_map=explicit_map or {}, threshold=similarity_threshold)
    # The build_candidates in our matcher expects quotes; create lightweight quotes containing events
    from app.core.models import MarketQuote as MQ
    candidates = matcher.build_candidates(
        [MQ("kalshi", "", q.event, "YES", 0.0, 0.0) for q in kalshi_quotes],
        [MQ("polymarket", "", q.event, "YES", 0.0, 0.0) for q in polymarket_quotes],
    )
    # Also do a local fuzzy pass to build a mapping dict
    from app.utils.text import similarity
    from app.utils.text import extract_numbers_window

    mapping: dict[str, str] = {}
    # Start with explicit mapping if provided
    if explicit_map:
        for k, v in explicit_map.items():
            mapping[key_event(k)] = key_event(v)
    # Add best fuzzy matches with a number-aware guard: if both events contain
    # numeric windows (e.g., years, thresholds), only accept if those windows match.
    for ek in unique_k_events:
        if key_event(ek) in mapping:
            continue
        best_sim = -1.0
        best_ep = None
        for ep in unique_p_events:
            s = similarity(ek, ep)
            # Number-aware guard
            nums_k = extract_numbers_window(ek)
            nums_p = extract_numbers_window(ep)
            if nums_k and nums_p and nums_k != nums_p:
                # Require matching numeric windows when both sides provide them
                continue
            if s > best_sim:
                best_sim = s
                best_ep = ep
        if best_ep and best_sim >= similarity_threshold:
            mapping[key_event(ek)] = key_event(best_ep)

    # For mapped pairs, compute arbs like in detect_arbs
    arbs: List[CrossExchangeArb] = []
    # Account for both taker and slippage bps (consistent with detect_arbs)
    total_bps = settings.fees.taker_bps + settings.risk.slippage_bps

    for ek_key, ep_key in mapping.items():
        k = k_by_event.get(ek_key)
        p = p_by_event.get(ep_key)
        if not k or not p:
            continue
        # Case K YES vs P NO
        if "YES" in k and "NO" in p:
            edge_bps = compute_edge_bps(k["YES"].price, p["NO"].price) - total_bps
            if edge_bps > 0:
                max_notional = min(
                    k["YES"].size * k["YES"].price,
                    p["NO"].size * (1 - p["NO"].price),
                    settings.risk.max_notional_per_leg,
                )
                gross_profit = edge_bps / 10000.0 * max_notional
                if gross_profit >= settings.risk.min_profit_usd:
                    arbs.append(
                        CrossExchangeArb(
                            event_key=f"{k['YES'].event} <-> {p['NO'].event}",
                            long=k["YES"],
                            short=p["NO"],
                            edge_bps=edge_bps,
                            gross_profit_usd=gross_profit,
                            max_notional=max_notional,
                        )
                    )
        # Case P YES vs K NO
        if "YES" in p and "NO" in k:
            edge_bps = compute_edge_bps(p["YES"].price, k["NO"].price) - total_bps
            if edge_bps > 0:
                max_notional = min(
                    p["YES"].size * p["YES"].price,
                    k["NO"].size * (1 - k["NO"].price),
                    settings.risk.max_notional_per_leg,
                )
                gross_profit = edge_bps / 10000.0 * max_notional
                if gross_profit >= settings.risk.min_profit_usd:
                    arbs.append(
                        CrossExchangeArb(
                            event_key=f"{p['YES'].event} <-> {k['NO'].event}",
                            long=p["YES"],
                            short=k["NO"],
                            edge_bps=edge_bps,
                            gross_profit_usd=gross_profit,
                            max_notional=max_notional,
                        )
                    )

    return arbs
