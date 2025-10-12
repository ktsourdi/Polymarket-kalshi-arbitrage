from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, List

from app.core.models import MarketQuote


class ExchangeConnector(ABC):
    name: str

    @abstractmethod
    async def fetch_quotes(self) -> List[MarketQuote]:
        raise NotImplementedError

    @abstractmethod
    def tradable_symbols(self) -> Iterable[str]:
        raise NotImplementedError
