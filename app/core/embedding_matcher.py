from __future__ import annotations

from typing import Iterable, List, Dict, Tuple, Callable, Optional, Set

import numpy as np

from app.core.models import MarketQuote, MatchCandidate
from app.utils.text import extract_numbers_window, extract_entity_tokens, extract_yis_actor_subject
from app.utils.emb_cache import embed_texts_openai_cached


def _tokens(text: str) -> Set[str]:
    import re
    t = text.lower()
    return set(re.findall(r"[a-z0-9]{3,}", t))


def _normalize(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=1, keepdims=True) + 1e-9
    return v / n


async def _embed_events(
    kalshi_events: List[str],
    poly_events: List[str],
    model: str = "text-embedding-3-small",
    progress_cb: Optional[Callable[[float], None]] = None,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, int], Dict[str, int]]:
    # Embed with cache (asynchronous)
    def _merge(vmap: Dict[str, np.ndarray], keys: List[str]) -> np.ndarray:
        arr = np.stack([vmap[k] for k in keys]).astype(np.float32)
        return _normalize(arr)

    if progress_cb:
        progress_cb(0.02)
    k_map = await embed_texts_openai_cached(kalshi_events, model=model, progress_cb=lambda f: progress_cb(0.02 + 0.38 * f) if progress_cb else None)
    p_map = await embed_texts_openai_cached(poly_events, model=model, progress_cb=lambda f: progress_cb(0.42 + 0.38 * f) if progress_cb else None)
    if progress_cb:
        progress_cb(0.82)
    k_vecs = _merge(k_map, kalshi_events)
    p_vecs = _merge(p_map, poly_events)
    k_index = {e: i for i, e in enumerate(kalshi_events)}
    p_index = {e: i for i, e in enumerate(poly_events)}
    return k_vecs, p_vecs, k_index, p_index


async def build_embedding_candidates_async(
    kalshi_quotes: Iterable[MarketQuote],
    polymarket_quotes: Iterable[MarketQuote],
    *,
    min_cosine: float = 0.82,
    max_kalshi_candidates: int = 800,
    top_k_per_poly: int = 3,
    model: str = "text-embedding-3-small",
    progress_cb: Optional[Callable[[float], None]] = None,
) -> List[MatchCandidate]:
    """Return MatchCandidate list using OpenAI embeddings + token guards.

    We iterate over Polymarket events (smaller set) and search a token-filtered
    subset of Kalshi events by cosine similarity. This keeps the number of
    comparisons manageable while preserving high recall.
    """

    # Unique event titles
    k_events = list({q.event for q in kalshi_quotes})
    p_events = list({q.event for q in polymarket_quotes})

    # Build token index on Kalshi events
    token_to_k: Dict[str, Set[str]] = {}
    nums_to_k: Dict[Tuple[int, ...], Set[str]] = {}
    for ek in k_events:
        for tk in _tokens(ek):
            token_to_k.setdefault(tk, set()).add(ek)
        nums = extract_numbers_window(ek)
        if nums:
            nums_to_k.setdefault(nums, set()).add(ek)

    # Embed all events (cached)
    k_vecs, p_vecs, k_index, p_index = await _embed_events(k_events, p_events, model=model, progress_cb=progress_cb)
    if progress_cb:
        progress_cb(0.84)

    candidates: List[MatchCandidate] = []
    total = max(1, len(p_events))
    for i, ep in enumerate(p_events):
        # Candidate Kalshi set by token overlap
        cand: Set[str] = set()
        toks = _tokens(ep)
        for tk in toks:
            if tk in token_to_k:
                cand.update(token_to_k[tk])
        if not cand:
            # If no token overlap, fallback to all
            cand.update(k_events)
        nums_p = extract_numbers_window(ep)
        if nums_p and nums_p in nums_to_k:
            cand &= nums_to_k[nums_p]

        # Hard cap + sort by entity overlap score
        if len(cand) > max_kalshi_candidates:
            ents_p = extract_entity_tokens(ep)
            def _score(ek: str) -> int:
                return len(ents_p & extract_entity_tokens(ek)) if ents_p else 0
            cand = set(sorted(cand, key=_score, reverse=True)[:max_kalshi_candidates])

        # Compute cosine similarities for this Polymarket event against the candidate Kalshi set
        if not cand:
            continue
        v_p = p_vecs[p_index[ep]][None, :]  # shape (1, d)
        idxs = np.array([k_index[ek] for ek in cand], dtype=np.int32)
        mat = k_vecs[idxs]  # shape (m, d)
        sims = (v_p @ mat.T).astype(np.float32).ravel()  # cosine since normalized
        if sims.size == 0:
            continue
        # Select top-k above threshold
        top_k = min(top_k_per_poly, sims.size)
        part = np.argpartition(-sims, top_k - 1)[:top_k]
        best_pairs = sorted([(int(idxs[j]), float(sims[j])) for j in part if sims[j] >= min_cosine], key=lambda x: x[1], reverse=True)
        for ki, score in best_pairs:
            ek = k_events[ki]
            # Numeric and entity guards re-checked (cheap)
            nums_k = extract_numbers_window(ek)
            if nums_k and nums_p and nums_k != nums_p:
                continue
            # Special-case Google Year in Search Actors: require identical subject
            subj_k = extract_yis_actor_subject(ek)
            subj_p2 = extract_yis_actor_subject(ep)
            if subj_k is not None or subj_p2 is not None:
                if not subj_k or not subj_p2 or subj_k != subj_p2:
                    continue
            ents_k = extract_entity_tokens(ek)
            ents_p = extract_entity_tokens(ep)
            # Require at least one shared entity token when both sides provide them
            if ents_k and ents_p and not (ents_k & ents_p):
                continue
            candidates.append(MatchCandidate(event_key=f"{ek} <-> {ep}", kalshi_market_id=None, polymarket_market_id=None, similarity=score))

        if progress_cb and (i + 1) % 50 == 0:
            progress_cb(0.84 + 0.16 * (i + 1) / total)

    if progress_cb:
        progress_cb(1.0)
    return candidates


async def build_event_mapping_by_embeddings(
    kalshi_quotes: Iterable[MarketQuote],
    polymarket_quotes: Iterable[MarketQuote],
    *,
    min_cosine: float = 0.82,
    model: str = "text-embedding-3-small",
    progress_cb: Optional[Callable[[float], None]] = None,
) -> Dict[str, str]:
    """Return mapping from Kalshi event -> best Polymarket event by cosine >= threshold."""
    k_events = list({q.event for q in kalshi_quotes})
    p_events = list({q.event for q in polymarket_quotes})

    # Token index for Kalshi (reuse from above)
    token_to_k: Dict[str, Set[str]] = {}
    nums_to_k: Dict[Tuple[int, ...], Set[str]] = {}
    for ek in k_events:
        for tk in _tokens(ek):
            token_to_k.setdefault(tk, set()).add(ek)
        nums = extract_numbers_window(ek)
        if nums:
            nums_to_k.setdefault(nums, set()).add(ek)

    # Embeddings (cached)
    k_vecs, p_vecs, k_index, p_index = await _embed_events(k_events, p_events, model=model, progress_cb=progress_cb)

    mapping: Dict[str, str] = {}
    total = max(1, len(p_events))
    for i, ep in enumerate(p_events):
        # Candidate Kalshi events for this Polymarket event
        cand: Set[str] = set()
        toks = _tokens(ep)
        for tk in toks:
            if tk in token_to_k:
                cand.update(token_to_k[tk])
        if not cand:
            cand.update(k_events)
        nums_p = extract_numbers_window(ep)
        if nums_p and nums_p in nums_to_k:
            cand &= nums_to_k[nums_p]
        if not cand:
            continue

        v_p = p_vecs[p_index[ep]][None, :]
        idxs = np.array([k_index[ek] for ek in cand], dtype=np.int32)
        mat = k_vecs[idxs]
        sims = (v_p @ mat.T).astype(np.float32).ravel()
        if sims.size == 0:
            continue
        j = int(np.argmax(sims))
        score = float(sims[j])
        if score >= min_cosine:
            ek = [*cand][j]  # idxs[j] maps back, but cand order differs; use idxs
            ek = k_events[int(idxs[j])]
            # Final guards
            nums_k = extract_numbers_window(ek)
            if nums_k and nums_p and nums_k != nums_p:
                pass
            else:
                ents_k = extract_entity_tokens(ek)
                ents_p = extract_entity_tokens(ep)
                if not (ents_k and ents_p) or (ents_k & ents_p):
                    mapping[ek.lower().strip()] = ep.lower().strip()

        if progress_cb and (i + 1) % 50 == 0:
            progress_cb((i + 1) / total)

    if progress_cb:
        progress_cb(1.0)
    return mapping


