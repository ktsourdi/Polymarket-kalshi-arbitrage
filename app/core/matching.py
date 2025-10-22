from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Tuple, Callable, Optional, Set
import random

from app.core.models import MarketQuote, MatchCandidate
from app.utils.text import similarity, extract_numbers_window, extract_entity_tokens


class EventMatcher:
    def __init__(self, explicit_map: Dict[str, str] | None = None, threshold: float = 0.72):
        self.explicit_map = {k.lower(): v for k, v in (explicit_map or {}).items()}
        self.threshold = threshold

    def build_candidates(
        self,
        kalshi_quotes: Iterable[MarketQuote],
        polymarket_quotes: Iterable[MarketQuote],
        *,
        limit_sources: Optional[int] = None,
        max_targets_per_source: int = 40,
        progress_cb: Optional[Callable[[float], None]] = None,
    ) -> List[MatchCandidate]:
        """Return best Polymarket match per Kalshi event using a token-indexed search.

        This avoids comparing every pair (O(N×M)) by first collecting target candidates
        via an inverted index on content tokens and numeric windows, then computing
        similarities only on those candidates. This dramatically reduces work on
        large datasets and prevents UI timeouts.
        """
        by_event_k: Dict[str, List[MarketQuote]] = defaultdict(list)
        by_event_p: Dict[str, List[MarketQuote]] = defaultdict(list)
        for q in kalshi_quotes:
            by_event_k[q.event].append(q)
        for q in polymarket_quotes:
            by_event_p[q.event].append(q)

        # Build lightweight inverted index for Polymarket events
        def _tokens(text: str) -> Set[str]:
            import re
            t = text.lower()
            toks = set(re.findall(r"[a-z0-9]{3,}", t))
            return toks

        token_to_events: Dict[str, Set[str]] = defaultdict(set)
        nums_to_events: Dict[Tuple[int, ...], Set[str]] = defaultdict(set)
        all_p_events = list(by_event_p.keys())
        for ep in all_p_events:
            for tok in _tokens(ep):
                token_to_events[tok].add(ep)
            nums = extract_numbers_window(ep)
            if nums:
                nums_to_events[nums].add(ep)

        k_events = list(by_event_k.keys())
        if limit_sources is not None:
            k_events = k_events[: int(limit_sources)]

        candidates: List[MatchCandidate] = []
        total = max(1, len(k_events))
        for idx, ek in enumerate(k_events):
            target = self.explicit_map.get(ek.lower())
            best_sim = -1.0
            best_event_pm = None

            # Collect candidate targets via token overlap and numeric window match
            cand: Set[str] = set()
            toks_k = _tokens(ek)
            for tk in toks_k:
                if tk in token_to_events:
                    cand.update(token_to_events[tk])
            # If no token candidates, fall back to a small sample to avoid empty search
            if not cand:
                if all_p_events:
                    # deterministic slice to keep behavior predictable
                    cand.update(all_p_events[: max_targets_per_source])

            # Enforce numeric window equality when both sides provide numbers
            nums_k = extract_numbers_window(ek)
            if nums_k:
                # Intersect with same-number candidates when index has them
                if nums_k in nums_to_events:
                    cand &= nums_to_events[nums_k]

            # Hard cap the number of candidates per source
            if len(cand) > max_targets_per_source:
                # Prefer stable order by similarity proxy: entity overlap size
                ents_k = extract_entity_tokens(ek)
                def _score(ep: str) -> int:
                    ents_p = extract_entity_tokens(ep)
                    return len(ents_k & ents_p) if ents_k and ents_p else 0
                cand = set(sorted(cand, key=_score, reverse=True)[:max_targets_per_source])

            for ep in cand:
                # Prefer explicit mapping when provided
                s = 1.0 if target and ep.lower() == target.lower() else similarity(ek, ep)
                # Require some entity overlap when possible
                ents_k = extract_entity_tokens(ek)
                ents_p = extract_entity_tokens(ep)
                if ents_k and ents_p and not (ents_k & ents_p):
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

            if progress_cb and (idx + 1) % 200 == 0:
                progress_cb((idx + 1) / total)

        if progress_cb:
            progress_cb(1.0)
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
