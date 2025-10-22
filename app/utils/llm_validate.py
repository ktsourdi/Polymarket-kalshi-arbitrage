from __future__ import annotations

from typing import Dict, Iterable, List, Tuple, Optional

import json
import os
from pathlib import Path


def _cache_paths(model: str) -> Path:
    base = Path(os.getenv("EMBED_CACHE_DIR") or Path.home() / ".cache" / "polykalshi")
    base.mkdir(parents=True, exist_ok=True)
    return base / f"llm_validate_{model.replace('/', '_')}.json"


def _load_cache(model: str) -> Dict[str, dict]:
    path = _cache_paths(model)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


def _save_cache(model: str, data: Dict[str, dict]) -> None:
    try:
        path = _cache_paths(model)
        path.write_text(json.dumps(data))
    except Exception:
        pass


def _key(a: str, b: str) -> str:
    return f"{a.strip()}|||{b.strip()}"


def validate_pairs_openai(
    pairs: List[Tuple[str, str]],
    model: str = "gpt-4o-mini",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    use_cache: bool = True,
) -> Dict[Tuple[str, str], dict]:
    """Use an OpenAI chat model to logically validate that two market titles
    refer to the same underlying event proposition and direction.

    Returns a mapping from (a,b) -> {same_event: bool, direction_consistent: bool, rationale: str}.
    Cached by exact title strings and model.
    """
    try:
        from openai import OpenAI
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("openai package not installed; run pip install openai") from exc

    client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"), base_url=base_url or os.getenv("OPENAI_BASE_URL") or None)
    cache = _load_cache(model) if use_cache else {}
    result: Dict[Tuple[str, str], dict] = {}

    to_query: List[Tuple[str, str]] = []
    for a, b in pairs:
        k = _key(a, b)
        if use_cache and k in cache:
            result[(a, b)] = cache[k]
        else:
            to_query.append((a, b))

    if to_query:
        # Batch pairs in a single prompt for efficiency
        items = []
        for i, (a, b) in enumerate(to_query):
            items.append({"id": i, "kalshi": a, "polymarket": b})
        sys = (
            "You are a strict validator for market title equivalence across two exchanges."
            " Decide if the two titles describe the SAME underlying event proposition and direction (YES/NO orientation)."
            " Consider entities, dates, numbers, and resolution criteria."
            " Reply with strict JSON: {results: [{id, same_event, direction_consistent, rationale}]}."
        )
        prompt = {
            "role": "user",
            "content": (
                "Validate these pairs. Titles are similar but may differ in phrasing."
                " Only mark same_event=true if a rational trader could hedge them as the same binary proposition."
                f" Pairs: {json.dumps(items)}"
            ),
        }
        resp = client.chat.completions.create(model=model, messages=[{"role": "system", "content": sys}, prompt], temperature=0)
        text = resp.choices[0].message.content or "{}"
        try:
            data = json.loads(text)
            rows = data.get("results") or []
        except Exception:
            rows = []
        by_id = {r.get("id"): r for r in rows if isinstance(r, dict)}
        for i, (a, b) in enumerate(to_query):
            r = by_id.get(i) or {"same_event": False, "direction_consistent": False, "rationale": "parse_error"}
            result[(a, b)] = r
            if use_cache:
                cache[_key(a, b)] = r
        _save_cache(model, cache)

    return result


