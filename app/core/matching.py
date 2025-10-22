from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Tuple

from app.core.models import MarketQuote, MatchCandidate
from app.utils.text import similarity, extract_numbers_window


class EventMatcher:
    def __init__(self, explicit_map: Dict[str, str] | None = None, threshold: float = 0.72):
        self.explicit_map = {k.lower(): v for k, v in (explicit_map or {}).items()}
        self.threshold = threshold

    def build_candidates(
        self, kalshi_quotes: Iterable[MarketQuote], polymarket_quotes: Iterable[MarketQuote]
    ) -> List[MatchCandidate]:
        by_event_k: Dict[str, List[MarketQuote]] = defaultdict(list)
        by_event_p: Dict[str, List[MarketQuote]] = defaultdict(list)
        for q in kalshi_quotes:
            by_event_k[q.event].append(q)
        for q in polymarket_quotes:
            by_event_p[q.event].append(q)

        candidates: List[MatchCandidate] = []
        for ek in by_event_k.keys():
            target = self.explicit_map.get(ek.lower())
            best_sim = -1.0
            best_event_pm = None
            for ep in by_event_p.keys():
                # Prefer explicit mapping when provided
                s = 1.0 if target and ep.lower() == target.lower() else similarity(ek, ep)
                # If both sides have numeric windows (e.g., dates, thresholds), enforce equality
                nums_k = extract_numbers_window(ek)
                nums_p = extract_numbers_window(ep)
                if nums_k and nums_p and nums_k != nums_p:
                    continue
                if s > best_sim:
                    best_sim = s
                    best_event_pm = ep
            if best_event_pm and best_sim >= self.threshold:
                candidates.append(
                    MatchCandidate(
                        event_key=f"{ek} <-> {best_event_pm}",
                        kalshi_market_id=None,
                        polymarket_market_id=None,
                        similarity=best_sim,
                    )
                )
        return candidates

    def pair_by_outcome(
        self, kalshi_quotes: Iterable[MarketQuote], polymarket_quotes: Iterable[MarketQuote]
    ) -> Dict[str, Tuple[List[MarketQuote], List[MarketQuote]]]:
        pairs: Dict[str, Tuple[List[MarketQuote], List[MarketQuote]]] = {}
        # Simple keying by normalized event text
        def key(event: str) -> str:
            return event.lower().strip()

        k_by = defaultdict(list)
        p_by = defaultdict(list)
        for q in kalshi_quotes:
            k_by[key(q.event)].append(q)
        for q in polymarket_quotes:
            p_by[key(q.event)].append(q)
        for ek, kqs in k_by.items():
            if ek in p_by:
                pairs[ek] = (kqs, p_by[ek])
        return pairs
