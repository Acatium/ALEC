"""Pure-Python string similarity utilities for entity resolution."""

from __future__ import annotations

import re


def normalize_entity_name(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    name = name.lower()
    name = re.sub(r"[:\-\(\)\"'/]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _tokens(name: str) -> set[str]:
    """Tokenize a normalized name into word tokens."""
    return set(normalize_entity_name(name).split())


def token_jaccard(a: str, b: str) -> float:
    """Jaccard similarity over normalized word tokens."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    intersection = ta & tb
    union = ta | tb
    return len(intersection) / len(union)


def containment_ratio(a: str, b: str) -> float:
    """Fraction of the shorter name's tokens present in the longer name."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if not shorter:
        return 0.0
    return len(shorter & longer) / len(shorter)


def name_similarity_score(
    candidate_name: str,
    candidate_aliases: list[str],
    query_name: str,
) -> float:
    """Combined string similarity score for entity matching.

    Returns the best score across name and all aliases using
    jaccard and containment heuristics.
    """
    jaccard = token_jaccard(candidate_name, query_name)
    contain = containment_ratio(candidate_name, query_name) * 0.9

    best = max(jaccard, contain)

    for alias in candidate_aliases:
        alias_jaccard = token_jaccard(alias, query_name)
        alias_contain = containment_ratio(alias, query_name) * 0.9
        best = max(best, alias_jaccard, alias_contain)

    return best
