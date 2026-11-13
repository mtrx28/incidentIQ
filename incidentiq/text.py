"""Small text helpers shared by the verifier and the keyword runbook search."""

import re

STOPWORDS = frozenset([
    "a", "an", "and", "are", "as", "at", "be", "been", "by", "for", "from", "has", "have", "in",
    "into", "is", "it", "its", "of", "on", "or", "than", "that", "the", "their", "then", "there",
    "these", "this", "those", "to", "was", "were", "which", "while", "with", "within", "would",
    "also", "after", "before", "during", "over", "under", "both", "each", "other", "some", "such",
    "only", "more", "most", "not", "no", "but", "if", "so", "can", "could", "may", "might", "will",
    "shall", "do", "does", "did", "being", "about", "above", "across", "against", "all", "any",
    "because", "between", "how", "out", "up", "down", "off",
])

_WORD = re.compile(r"\d+(?:\.\d+)?|[a-z]+")


def words(text: str) -> list[str]:
    """Lowercase words and numbers (19.54 stays whole; error_rate_pct becomes three words)."""
    return _WORD.findall(text.lower())
