from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

import math

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except Exception:  # pragma: no cover - optional dependency
    TfidfVectorizer = None  # type: ignore
    cosine_similarity = None  # type: ignore

from app.utils.text import normalize_text, extract_numbers_window


def build_tfidf_map(
    sources: Iterable[str],
    targets: Iterable[str],
    min_similarity: float = 0.6,
    strict_numbers: bool = True,
) -> Dict[str, Tuple[str, float]]:
    """Build a mapping from each source string to the best target by TF-IDF cosine.

    Returns a dict: original_source -> (best_target, score)
    If sklearn is unavailable, returns an empty mapping.
    """
    if TfidfVectorizer is None or cosine_similarity is None:
        return {}

    src_list = list(dict.fromkeys(sources))
    tgt_list = list(dict.fromkeys(targets))
    if not src_list or not tgt_list:
        return {}

    corpus = [normalize_text(s) for s in src_list] + [normalize_text(t) for t in tgt_list]
    vec = TfidfVectorizer(ngram_range=(1, 3), min_df=1)
    X = vec.fit_transform(corpus)
    src_X = X[: len(src_list)]
    tgt_X = X[len(src_list) :]

    sims = cosine_similarity(src_X, tgt_X)
    mapping: Dict[str, Tuple[str, float]] = {}
    for i, s_orig in enumerate(src_list):
        best_j = -1
        best = -math.inf
        for j, _ in enumerate(tgt_list):
            score = float(sims[i, j])
            if strict_numbers:
                nums_s = extract_numbers_window(s_orig)
                nums_t = extract_numbers_window(tgt_list[j])
                if nums_s and nums_t and nums_s != nums_t:
                    continue
            if score > best:
                best = score
                best_j = j
        if best_j >= 0 and best >= min_similarity:
            mapping[s_orig] = (tgt_list[best_j], best)
    return mapping



