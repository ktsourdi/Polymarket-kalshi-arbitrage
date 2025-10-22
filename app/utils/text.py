import re
import unicodedata
from difflib import SequenceMatcher
from typing import Tuple, Set


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
}


def extract_entity_tokens(value: str) -> Set[str]:
    """Extract crude entity-like tokens (capitalized or acronyms).

    This is a lightweight heuristic to reduce obvious mismatches without heavy NLP.
    """
    raw_tokens = re.findall(r"[A-Z][a-zA-Z]+|[A-Z]{2,}|[A-Z][a-z]+\.[A-Z][a-z]+", value)
    ents: Set[str] = set()
    for t in raw_tokens:
        k = t.lower()
        if k in _STOP_ENTS:
            continue
        ents.add(k)
    return ents
