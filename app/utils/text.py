import re
import unicodedata
from difflib import SequenceMatcher
from typing import Tuple


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
