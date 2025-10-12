from __future__ import annotations

from dataclasses import dataclass
from typing import List

from app.core.models import CrossExchangeArb, TwoBuyArb
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


class LiveExecutor:
    def __init__(self, kalshi_client, polymarket_client):
        self.kalshi = kalshi_client
        self.polymarket = polymarket_client

    async def execute_two_buy(self, opportunities: List[TwoBuyArb]) -> List[Fill]:
        fills: List[Fill] = []
        for opp in opportunities:
            # Determine which exchange has YES vs NO
            if opp.buy_yes.exchange == "kalshi":
                yes_client = self.kalshi
            else:
                yes_client = self.polymarket
            if opp.buy_no.exchange == "kalshi":
                no_client = self.kalshi
            else:
                no_client = self.polymarket

            # For now, place at displayed prices and contracts; production should compute safe limits
            yes_resp = await yes_client.place_limit_order(
                market_id=opp.buy_yes.market_id,
                outcome="YES",
                side="BUY",
                price=opp.buy_yes.price,
                size=opp.contracts,
            )
            no_resp = await no_client.place_limit_order(
                market_id=opp.buy_no.market_id,
                outcome="NO",
                side="BUY",
                price=opp.buy_no.price,
                size=opp.contracts,
            )

            logger.info(
                "Live orders submitted for %s | YES id=%s | NO id=%s",
                opp.event_key,
                yes_resp.get("id"),
                no_resp.get("id"),
            )

            fills.append(
                Fill(
                    exchange=opp.buy_yes.exchange,
                    market_id=opp.buy_yes.market_id,
                    side="BUY",
                    price=opp.buy_yes.price,
                    size=opp.contracts,
                )
            )
            fills.append(
                Fill(
                    exchange=opp.buy_no.exchange,
                    market_id=opp.buy_no.market_id,
                    side="BUY",
                    price=opp.buy_no.price,
                    size=opp.contracts,
                )
            )

        return fills
