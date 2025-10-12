from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExchangeAuth:
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    base_url: Optional[str] = None


@dataclass
class Fees:
    taker_bps: float = 20.0  # 1 bps = 0.01%
    withdrawal_flat: float = 0.0


@dataclass
class Risk:
    max_notional_per_leg: float = 500.0
    min_profit_usd: float = 2.0
    slippage_bps: float = 10.0


@dataclass
class Settings:
    kalshi: ExchangeAuth = field(default_factory=ExchangeAuth)
    polymarket: ExchangeAuth = field(default_factory=ExchangeAuth)
    fees: Fees = field(default_factory=Fees)
    risk: Risk = field(default_factory=Risk)
    env: str = "dev"


settings = Settings()