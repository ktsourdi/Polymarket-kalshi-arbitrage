import os
import hashlib
import json
from pathlib import Path
from typing import List, Dict, Callable, Tuple, Optional

import numpy as np

try:
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore


CACHE_DIR = Path(os.getenv("EMB_CACHE_DIR", ".cache/openai"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _hash(text: str) -> str:
    h = hashlib.sha256()
    h.update(text.strip().lower().encode())
    return h.hexdigest()


def _cache_path(h: str) -> Path:
    return CACHE_DIR / f"{h}.json"


def load_cached(texts: List[str]) -> Tuple[Dict[str, np.ndarray], List[str]]:
    """Return (cached_vectors, missing_texts)."""
    cached: Dict[str, np.ndarray] = {}
    missing: List[str] = []
    for t in texts:
        p = _cache_path(_hash(t))
        if p.exists():
            try:
                with p.open("r") as f:
                    data = json.load(f)
                vec = np.array(data["embedding"], dtype=np.float32)
                cached[t] = vec
            except Exception:
                missing.append(t)
        else:
            missing.append(t)
    return cached, missing


def save_cached(pairs: Dict[str, np.ndarray]):
    for t, vec in pairs.items():
        p = _cache_path(_hash(t))
        try:
            with p.open("w") as f:
                json.dump({"embedding": vec.tolist()}, f)
        except Exception:
            # best-effort cache
            pass


async def embed_texts_openai_cached(
    texts: List[str],
    model: str = "text-embedding-3-small",
    progress_cb: Optional[Callable[[float], None]] = None,
) -> Dict[str, np.ndarray]:
    """Embed texts via OpenAI with on-disk cache."""
    import asyncio
    if OpenAI is None:
        raise RuntimeError("openai package not installed; run pip install openai")

    cached, missing = load_cached(texts)
    out: Dict[str, np.ndarray] = dict(cached)
    if not missing:
        return out

    CHUNK = 96  # stay below 100/request
    client = OpenAI()
    for i in range(0, len(missing), CHUNK):
        batch = missing[i : i + CHUNK]
        resp = client.embeddings.create(model=model, input=batch)
        for inp, emb in zip(batch, resp.data):
            vec = np.asarray(emb.embedding, dtype=np.float32)
            out[inp] = vec
        save_cached({inp: out[inp] for inp in batch})
        if progress_cb:
            progress_cb(min(1.0, (i + CHUNK) / len(missing)))
    return out
