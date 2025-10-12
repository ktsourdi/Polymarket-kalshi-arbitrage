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
    for q in kalshi_quotes:
        k_by_event[q.event][q.outcome] = q
    for q in polymarket_quotes:
        p_by_event[q.event][q.outcome] = q

    arbs: List[CrossExchangeArb] = []
    for event in set(k_by_event.keys()) & set(p_by_event.keys()):
        k = k_by_event[event]
        p = p_by_event[event]
        if "YES" in k and "NO" in p:
            edge_bps = compute_edge_bps(k["YES"].price, p["NO"].price) - settings.fees.taker_bps
            if edge_bps > 0:
                max_notional = min(k["YES"].size * k["YES"].price, p["NO"].size * (1 - p["NO"].price), settings.risk.max_notional_per_leg)
                gross_profit = edge_bps / 10000.0 * max_notional
                if gross_profit >= settings.risk.min_profit_usd:
                    arbs.append(
                        CrossExchangeArb(
                            event_key=event,
                            long=k["YES"],
                            short=p["NO"],
                            edge_bps=edge_bps,
                            gross_profit_usd=gross_profit,
                            max_notional=max_notional,
                        )
                    )
        if "YES" in p and "NO" in k:
            edge_bps = compute_edge_bps(p["YES"].price, k["NO"].price) - settings.fees.taker_bps
            if edge_bps > 0:
                max_notional = min(p["YES"].size * p["YES"].price, k["NO"].size * (1 - k["NO"].price), settings.risk.max_notional_per_leg)
                gross_profit = edge_bps / 10000.0 * max_notional
                if gross_profit >= settings.risk.min_profit_usd:
                    arbs.append(
                        CrossExchangeArb(
                            event_key=event,
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
    for event in set(k_by_event.keys()) & set(p_by_event.keys()):
        k = k_by_event[event]
        p = p_by_event[event]
        # Case A: buy YES on Kalshi, buy NO on Polymarket
        if "YES" in k and "NO" in p:
            sum_price = k["YES"].price + p["NO"].price
            # Fees scale with notional, so subtract fee on each leg proportional to price
            edge = 1.0 - sum_price - taker_fee * (k["YES"].price + p["NO"].price)
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
            edge = 1.0 - sum_price - taker_fee * (p["YES"].price + k["NO"].price)
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
