import re
import unicodedata
from difflib import SequenceMatcher
from typing import Tuple, Set, Dict, List


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.lower()
    value = re.sub(r"[\u2018\u2019]", "'", value)
    value = re.sub(r"[\u201c\u201d]", '"', value)
    value = re.sub(r"[^a-z0-9\s]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def similarity(a: str, b: str) -> float:
    na = normalize_text(a)
    nb = normalize_text(b)
    return SequenceMatcher(None, na, nb).ratio()


def extract_numbers_window(value: str) -> Tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d{1,4}", value))


_STOP_ENTS = {
    "will",
    "the",
    "of",
    "in",
    "on",
    "to",
    "and",
    "or",
    "for",
    "by",
    "at",
    # Months
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    # Common capitalized words that shouldn't be treated as unique entities
    "google",
    "year",
    "search",
    "global",
    "actors",
    "people",
    "rank",
    "ranked",
    "globally",
}


def extract_entity_tokens(value: str) -> Set[str]:
    """Extract crude entity-like tokens (capitalized or acronyms).

    This is a lightweight heuristic to reduce obvious mismatches without heavy NLP.
    Focuses on capturing person names and other unique identifiers while filtering
    out common capitalized words.
    """
    raw_tokens = re.findall(r"[A-Z][a-zA-Z]+|[A-Z]{2,}|[A-Z][a-z]+\.[A-Z][a-z]+", value)
    ents: Set[str] = set()
    for t in raw_tokens:
        k = t.lower()
        if k in _STOP_ENTS:
            continue
        ents.add(k)
    return ents


# --- Key-term extraction and overlap scoring ---

def _simple_tokenize(text: str) -> List[str]:
    """Lightweight tokenizer used for fallback keyword extraction.

    Produces lowercase alphanumeric tokens of length >= 3.
    """
    t = normalize_text(text)
    return [tok for tok in re.findall(r"[a-z0-9]{3,}", t)]


def build_key_terms_index(texts: List[str], top_k: int = 8) -> Dict[str, Dict[str, float]]:
    """Return per-text top key terms with normalized weights.

    Uses TF‑IDF (1-2grams, english stopwords) when scikit-learn is available.
    Falls back to simple frequency on tokens otherwise.

    Returns a mapping: original_text -> {term: weight_in_[0,1]}
    where weights for each text sum to 1 (or 0 if no terms).
    """
    # De-duplicate but keep original instances mapping
    unique_texts: List[str] = list(dict.fromkeys(texts))
    if not unique_texts:
        return {}

    # Try TF-IDF path
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore

        # Normalize once for vocabulary construction
        normed = [normalize_text(t) for t in unique_texts]
        vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", min_df=1)
        X = vectorizer.fit_transform(normed)
        vocab = vectorizer.get_feature_names_out()

        result: Dict[str, Dict[str, float]] = {}
        for i, orig in enumerate(unique_texts):
            row = X.getrow(i)
            if row.nnz == 0:
                result[orig] = {}
                continue
            # Get top_k non-zero indices by TF-IDF weight
            nz_idx = row.indices
            nz_data = row.data
            # Pair, sort by weight desc, take top_k
            pairs = sorted(zip(nz_idx, nz_data), key=lambda p: p[1], reverse=True)[: max(1, top_k)]
            weights = {str(vocab[j]): float(w) for j, w in pairs}
            s = sum(weights.values())
            if s > 0:
                weights = {k: v / s for k, v in weights.items()}
            result[orig] = weights
        return result
    except Exception:
        # Fallback: simple token frequency weighting
        result: Dict[str, Dict[str, float]] = {}
        for orig in unique_texts:
            toks = _simple_tokenize(orig)
            if not toks:
                result[orig] = {}
                continue
            # crude stoplist for generic words
            stop = {
                "will","the","and","for","with","from","that","this","have","has","was","were","are","is","can","may","might","could","should","would","shall","than","then","into","onto","about","after","before","most","more","less",
            }
            freq: Dict[str, int] = {}
            for t in toks:
                if t in stop:
                    continue
                freq[t] = freq.get(t, 0) + 1
            # pick top_k
            items = sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[: max(1, top_k)]
            total = float(sum(v for _, v in items)) or 1.0
            result[orig] = {k: v / total for k, v in items}
        return result


def weighted_key_overlap(a_terms: Dict[str, float], b_terms: Dict[str, float]) -> float:
    """Compute weighted Jaccard-like overlap between two key-term dicts.

    Both inputs map term -> weight (weights ideally sum to 1 per dict).
    Returns value in [0, 1]. If both are empty, returns 0.0.
    """
    if not a_terms or not b_terms:
        return 0.0
    shared = set(a_terms.keys()) & set(b_terms.keys())
    if not shared:
        return 0.0
    num = sum(min(a_terms[t], b_terms[t]) for t in shared)
    den = sum(a_terms.values()) + sum(b_terms.values()) - sum(max(a_terms.get(t, 0.0), b_terms.get(t, 0.0)) for t in shared)
    # When weights are normalized to 1, denominator simplifies to 2 - sum(max(...)), but compute robustly
    # Guard against tiny denominators
    if den <= 1e-12:
        return 0.0
    return max(0.0, min(1.0, num / den))
