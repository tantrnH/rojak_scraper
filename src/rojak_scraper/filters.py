"""Heuristics for classifying Malay-English "rojak" sentences."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Set

from langdetect import DetectorFactory, LangDetectException, detect_langs

DetectorFactory.seed = 7

MALAY_COMMON_WORDS: Set[str] = {
    "ada",
    "akan",
    "aku",
    "anda",
    "atau",
    "bagi",
    "baik",
    "banyak",
    "baru",
    "begitu",
    "boleh",
    "buat",
    "dah",
    "dalam",
    "dan",
    "dengan",
    "dia",
    "diri",
    "guna",
    "hanya",
    "hingga",
    "jadi",
    "jika",
    "juga",
    "kali",
    "kami",
    "kamu",
    "kata",
    "kecil",
    "keluarga",
    "kemudian",
    "kerana",
    "kita",
    "lagi",
    "makan",
    "mana",
    "masa",
    "masih",
    "mesti",
    "mereka",
    "orang",
    "perlu",
    "pula",
    "saja",
    "sangat",
    "saya",
    "sebab",
    "serta",
    "sini",
    "sudah",
    "suka",
    "supaya",
    "tak",
    "tidak",
    "untuk",
    "yang",
}

MALAY_SUFFIXES: Sequence[str] = ("lah", "kah", "nya", "pun", "kan", "ke", "je")

ENGLISH_COMMON_WORDS: Set[str] = {
    "i",
    "me",
    "my",
    "we",
    "us",
    "you",
    "they",
    "them",
    "the",
    "this",
    "that",
    "is",
    "are",
    "was",
    "were",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "and",
    "or",
    "but",
    "if",
    "because",
    "with",
    "without",
    "for",
    "from",
    "very",
    "really",
    "good",
    "bad",
    "love",
    "like",
    "nice",
    "thank",
    "thanks",
    "fast",
    "slow",
    "delivery",
    "seller",
    "price",
    "packaging",
    "quality",
    "product",
    "recommend",
    "received",
    "already",
    "again",
    "buy",
    "bought",
    "using",
    "use",
    "super",
    "awesome",
    "happy",
    "okay",
    "ok",
    "best",
    "worst",
    "item",
    "worth",
    "cheap",
    "expensive",
    "size",
    "fit",
    "service",
    "original",
}

WORD_RE = re.compile(r"[A-Za-z']+")


@dataclass
class RojakDecision:
    """Detailed decision for a single comment."""

    is_rojak: bool
    malay_ratio: float
    english_count: int
    total_words: int


def _tokenise(text: str) -> List[str]:
    return [token.lower() for token in WORD_RE.findall(text)]


def _is_malay_word(word: str) -> bool:
    if word in MALAY_COMMON_WORDS:
        return True
    return any(word.endswith(suffix) for suffix in MALAY_SUFFIXES)


def _is_english_word(word: str) -> bool:
    if word in ENGLISH_COMMON_WORDS:
        return True
    if word.endswith(("ing", "ed")) and len(word) > 3:
        return True
    if word in MALAY_COMMON_WORDS:
        return False
    return False


def classify_rojak(
    text: str,
    *,
    min_length: int = 10,
    min_words: int = 3,
    min_english_words: int = 2,
    malay_ratio_threshold: float = 0.6,
) -> RojakDecision:
    """Return a :class:`RojakDecision` for the provided text."""

    stripped = text.strip()
    if len(stripped) < min_length:
        return RojakDecision(False, 0.0, 0, 0)

    words = _tokenise(stripped)
    if len(words) < min_words:
        return RojakDecision(False, 0.0, 0, len(words))

    malay_hits = sum(1 for word in words if _is_malay_word(word))
    english_hits = sum(1 for word in words if _is_english_word(word))
    malay_ratio = malay_hits / len(words) if words else 0.0

    if english_hits < min_english_words or malay_ratio < malay_ratio_threshold:
        return RojakDecision(False, malay_ratio, english_hits, len(words))

    try:
        languages = detect_langs(stripped)
    except LangDetectException:
        languages = []

    malay_probability = 0.0
    for item in languages:
        if item.lang in {"ms", "id"}:
            malay_probability = max(malay_probability, item.prob)
    if languages and malay_probability < 0.4:
        return RojakDecision(False, malay_ratio, english_hits, len(words))

    return RojakDecision(True, malay_ratio, english_hits, len(words))


def filter_rojak_sentences(texts: Iterable[str]) -> List[str]:
    """Filter an iterable of candidate sentences down to those considered rojak."""

    results: List[str] = []
    seen: Set[str] = set()
    for text in texts:
        normalised = " ".join(text.split())
        if normalised.lower() in seen:
            continue
        decision = classify_rojak(normalised)
        if decision.is_rojak:
            results.append(normalised)
            seen.add(normalised.lower())
    return results

