"""Core data models for market quotes and arbitrage opportunities.

This module defines the fundamental data structures used throughout the application
for representing market data, matching candidates, and arbitrage opportunities.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional

Side = Literal["YES", "NO"]


@dataclass(frozen=True)
class MarketQuote:
    exchange: str
    market_id: str
    event: str
    outcome: Side
    price: float  # in USD from 0 to 1
    size: float  # maximum fillable contracts (notional = price * size)
    end_date: Optional[datetime] = None  # Market resolution date


@dataclass(frozen=True)
class CrossExchangeArb:
    event_key: str
    long: MarketQuote
    short: MarketQuote
    edge_bps: float
    gross_profit_usd: float
    max_notional: float


@dataclass(frozen=True)
class MatchCandidate:
    event_key: str
    kalshi_market_id: Optional[str]
    polymarket_market_id: Optional[str]
    similarity: float


@dataclass(frozen=True)
class TwoBuyArb:
    """Represents a buy-YES on one exchange and buy-NO on the other.

    Profit per contract ≈ 1 - (yes_price + no_price) minus fees and slippage.
    """

    event_key: str
    buy_yes: MarketQuote
    buy_no: MarketQuote
    sum_price: float
    edge_bps: float
    contracts: float
    gross_profit_usd: float
