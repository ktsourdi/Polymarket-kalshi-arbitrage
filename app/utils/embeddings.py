from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple, Callable

import math
import os
import json
from pathlib import Path

from app.utils.text import extract_numbers_window


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    num = 0.0
    da = 0.0
    db = 0.0
    for x, y in zip(a, b):
        num += x * y
        da += x * x
        db += y * y
    if da == 0.0 or db == 0.0:
        return 0.0
    return num / (da ** 0.5 * db ** 0.5)


def _chunk(seq: List[str], n: int) -> List[List[str]]:
    return [seq[i : i + n] for i in range(0, len(seq), n)]


def _cache_paths(model: str) -> Tuple[Path, Path]:
    base = Path(os.getenv("EMBED_CACHE_DIR") or Path.home() / ".cache" / "polykalshi")
    base.mkdir(parents=True, exist_ok=True)
    return base, base / f"embeddings_{model.replace('/', '_')}.json"


def embed_openai(
    texts: List[str],
    model: str = "text-embedding-3-small",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    batch_size: int = 128,
    use_cache: bool = True,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> List[List[float]]:
    """Return embeddings for texts using OpenAI Embeddings API.

    Reads API key from OPENAI_API_KEY if not provided. Optional base_url allows
    using compatible providers.
    """
    try:
        from openai import OpenAI
    except Exception as exc:  # pragma: no cover - optional dependency not installed
        raise RuntimeError("openai package not installed; run pip install openai") from exc

    key = api_key or os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    client = OpenAI(api_key=key, base_url=base_url or os.getenv("OPENAI_BASE_URL") or None)

    # Load cache
    cache_data: Dict[str, List[float]] = {}
    seen: Dict[str, List[float]] = {}
    if use_cache:
        _, cache_file = _cache_paths(model)
        if cache_file.exists():
            try:
                cache_data = json.loads(cache_file.read_text())
            except Exception:
                cache_data = {}

    # Prepare batches with cache hits/misses
    misses: List[str] = []
    hits = 0
    for t in texts:
        key_t = t.strip()
        if use_cache and key_t in cache_data:
            seen[key_t] = cache_data[key_t]
            hits += 1
        else:
            misses.append(key_t)
    if progress_cb is not None and len(texts) > 0:
        progress_cb(min(1.0, hits / float(len(texts))))

    # Embed misses
    miss_vectors: Dict[str, List[float]] = {}
    for chunk in _chunk(misses, max(1, batch_size)):
        if not chunk:
            continue
        resp = client.embeddings.create(model=model, input=chunk)
        for i, item in enumerate(resp.data):
            miss_vectors[chunk[i]] = list(item.embedding)
        if progress_cb is not None and len(texts) > 0:
            done = min(len(texts), hits + len(miss_vectors))
            progress_cb(min(1.0, done / float(len(texts))))

    # Merge into cache and persist
    if use_cache:
        cache_data.update(miss_vectors)
        try:
            _, cache_file = _cache_paths(model)
            cache_file.write_text(json.dumps(cache_data))
        except Exception:
            pass

    # Return in original order
    vectors: List[List[float]] = []
    for t in texts:
        key_t = t.strip()
        vec = seen.get(key_t) or miss_vectors.get(key_t)
        if vec is None:
            vec = []
        vectors.append(vec)
    return vectors


def build_embedding_map_openai(
    sources: Iterable[str],
    targets: Iterable[str],
    min_similarity: float = 0.6,
    strict_numbers: bool = True,
    model: str = "text-embedding-3-small",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    batch_size: int = 128,
    use_cache: bool = True,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> Dict[str, Tuple[str, float]]:
    """Map each source to best target via OpenAI embeddings cosine.

    Returns mapping original_source -> (best_target, score)
    """
    src_list = list(dict.fromkeys(sources))
    tgt_list = list(dict.fromkeys(targets))
    if not src_list or not tgt_list:
        return {}

    def _p1(f: float):
        if progress_cb is not None:
            progress_cb(0.5 * max(0.0, min(1.0, f)))
    src_emb = embed_openai(
        src_list,
        model=model,
        api_key=api_key,
        base_url=base_url,
        batch_size=batch_size,
        use_cache=use_cache,
        progress_cb=_p1,
    )
    def _p2(f: float):
        if progress_cb is not None:
            progress_cb(0.5 + 0.5 * max(0.0, min(1.0, f)))
    tgt_emb = embed_openai(
        tgt_list,
        model=model,
        api_key=api_key,
        base_url=base_url,
        batch_size=batch_size,
        use_cache=use_cache,
        progress_cb=_p2,
    )

    mapping: Dict[str, Tuple[str, float]] = {}
    for i, s_orig in enumerate(src_list):
        best_j = -1
        best = -math.inf
        nums_s = extract_numbers_window(s_orig) if strict_numbers else ()
        for j, t_orig in enumerate(tgt_list):
            if strict_numbers:
                nums_t = extract_numbers_window(t_orig)
                if nums_s and nums_t and nums_s != nums_t:
                    continue
            score = _cosine(src_emb[i], tgt_emb[j])
            if score > best:
                best = score
                best_j = j
        if best_j >= 0 and best >= min_similarity:
            mapping[s_orig] = (tgt_list[best_j], float(best))
    return mapping


