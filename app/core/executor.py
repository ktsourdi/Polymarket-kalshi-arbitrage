from __future__ import annotations

from dataclasses import dataclass
from typing import List

from app.core.models import CrossExchangeArb
from app.utils.logging import get_logger


logger = get_logger("executor")


@dataclass
class Fill:
    exchange: str
    market_id: str
    side: str
    price: float
    size: float


class PaperExecutor:
    def execute(self, opportunities: List[CrossExchangeArb]) -> List[Fill]:
        fills: List[Fill] = []
        for opp in opportunities:
            size_yes = opp.max_notional / opp.long.price if opp.long.price > 0 else 0
            size_no = opp.max_notional / (1 - opp.short.price) if opp.short.price < 1 else 0
            fills.append(
                Fill(
                    exchange=opp.long.exchange,
                    market_id=opp.long.market_id,
                    side="BUY",
                    price=opp.long.price,
                    size=size_yes,
                )
            )
            fills.append(
                Fill(
                    exchange=opp.short.exchange,
                    market_id=opp.short.market_id,
                    side="SELL",
                    price=opp.short.price,
                    size=size_no,
                )
            )
            logger.info(
                "Executed paper trade for %s: long %s@%.2f, short %s@%.2f, notional=%.2f, profit=$%.2f",
                opp.event_key,
                opp.long.exchange,
                opp.long.price,
                opp.short.exchange,
                opp.short.price,
                opp.max_notional,
                opp.gross_profit_usd,
            )
        return fills
