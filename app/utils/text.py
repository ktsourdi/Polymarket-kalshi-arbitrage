import re
import unicodedata
from difflib import SequenceMatcher
from typing import Tuple, Set, Optional


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
    raw_tokens = re.findall(r"[A-Z][a-zA-Z]+|[A-Z]{2,}|[A-Z][a-z]+\.[A-Z][a-z]+", value)
    ents: Set[str] = set()
    for t in raw_tokens:
        k = t.lower()
        if k in _STOP_ENTS:
            continue
        ents.add(k)
    return ents


def extract_yis_actor_subject(value: str) -> Optional[str]:
    """Extract normalized subject name for Google 'Year in Search' Actors titles.

    Returns lowercase normalized token string or None when pattern not detected.
    """
    if not value:
        return None
    low = value.lower()
    if ("year in search" not in low) or ("actor" not in low and "actors" not in low):
        return None
    m = re.search(r"will\s+(.+?)\s+be\b", value, flags=re.IGNORECASE)
    if not m:
        return None
    subj = m.group(1).strip()
    if not subj:
        return None
    return normalize_text(subj)
