"""Shared keyword search helpers for inventory filtering."""
from typing import List, Tuple


def escape_like(term: str) -> str:
    """Escape SQL LIKE wildcards so user input is treated literally."""
    return (
        term.replace("[", "[[]")
        .replace("%", "[%]")
        .replace("_", "[_]")
    )


def split_keywords(search_term: str) -> List[str]:
    """Split a search string into non-empty keywords."""
    return [k for k in (search_term or "").strip().split() if k]


def build_keyword_filter(columns: List[str], search_term: str) -> Tuple[str, List[str]]:
    """
    Build a multi-keyword AND filter.

    Each keyword must match at least one of the given columns via LIKE %keyword%.
    Example: "blue shirt" → ItemNum/ItemName must contain both "blue" and "shirt".

    Returns (sql_where_fragment, params).
    Empty search returns ("1=1", []).
    """
    keywords = split_keywords(search_term)
    if not keywords:
        return "1=1", []

    clauses: List[str] = []
    params: List[str] = []
    for kw in keywords:
        escaped = escape_like(kw)
        col_parts = " OR ".join(f"{col} LIKE ?" for col in columns)
        clauses.append(f"({col_parts})")
        for _ in columns:
            params.append(f"%{escaped}%")

    return " AND ".join(clauses), params
