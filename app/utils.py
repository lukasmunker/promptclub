from __future__ import annotations

import re
from typing import Any, Iterable


def compact_whitespace(text: str | None) -> str | None:
    if not text:
        return text
    return re.sub(r"\s+", " ", text).strip()


def unique_preserve_order(items: Iterable[str]) -> list[str]:
    seen = set()
    output: list[str] = []
    for item in items:
        if not item:
            continue
        if item not in seen:
            seen.add(item)
            output.append(item)
    return output


def ensure_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def dig(obj: dict | list | None, path: list[str | int], default=None):
    cur = obj
    for key in path:
        if cur is None:
            return default
        if isinstance(cur, dict) and isinstance(key, str):
            cur = cur.get(key)
        elif isinstance(cur, list) and isinstance(key, int):
            if key >= len(cur):
                return default
            cur = cur[key]
        else:
            return default
    return cur if cur is not None else default


def split_inclusion_exclusion(criteria: str | None) -> tuple[str | None, str | None]:
    if not criteria:
        return None, None

    text = criteria.strip()
    lower = text.lower()

    inc_idx = lower.find("inclusion criteria")
    exc_idx = lower.find("exclusion criteria")

    if inc_idx == -1 and exc_idx == -1:
        return text, None

    inclusion = None
    exclusion = None

    if inc_idx != -1 and exc_idx != -1:
        if inc_idx < exc_idx:
            inclusion = text[inc_idx:exc_idx].strip()
            exclusion = text[exc_idx:].strip()
        else:
            exclusion = text[exc_idx:inc_idx].strip()
            inclusion = text[inc_idx:].strip()
    elif inc_idx != -1:
        inclusion = text[inc_idx:].strip()
    elif exc_idx != -1:
        exclusion = text[exc_idx:].strip()

    return inclusion, exclusion


def normalize_text_match(value: str | None) -> str:
    return (value or "").strip().lower()


def matches_any_text(candidates: list[str], needle: str | None) -> bool:
    if not needle:
        return True
    n = normalize_text_match(needle)
    return any(n in normalize_text_match(x) for x in candidates)