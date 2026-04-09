from __future__ import annotations

from collections.abc import Iterable
from secrets import token_hex
from typing import Any
from urllib.parse import urlparse

from app.utils import compact_whitespace


def build_citation_layer(citations: Iterable[Any]) -> dict[str, Any]:
    """Build a lightweight citation layer without the separate sources drawer UI."""
    references: list[dict[str, Any]] = []
    seen: set[tuple[str | None, str | None, str | None, str | None]] = set()
    layer_id = token_hex(4)

    for citation in citations or []:
        source = _field(citation, "source") or "Source"
        citation_id = _field(citation, "id")
        url = _field(citation, "url")
        title = _field(citation, "title")

        key = (source, citation_id, url, title)
        if key in seen:
            continue
        seen.add(key)

        label = _short_label(source, title, citation_id, url)
        index = len(references) + 1
        chatgpt_marker = f"[{index}]"
        markdown_marker = f"[{chatgpt_marker}]({url})" if url else chatgpt_marker
        hover_card = _hover_card(source, title, citation_id, url, label)
        citation_key = f"cite_{layer_id}_{index}"

        references.append(
            {
                "index": index,
                "marker": chatgpt_marker,
                "citation_key": citation_key,
                "markdown_marker": markdown_marker,
                "label": label,
                "source": source,
                "id": citation_id,
                "url": url,
                "title": title,
                "tooltip": hover_card["tooltip"],
                "hover_card": hover_card,
            }
        )

    return {
        "style": "chatgpt_markdown",
        "display_style": "inline_references_only",
        "render_hints": {
            "preferred": "inline_reference",
            "fallback": "markdown_link",
            "marker_shape": "inline_numbered_bracket",
            "client_should_renumber": True,
        },
        "numbering": {
            "scope": "tool_result",
            "client_should_renumber": True,
            "dedupe_key": "citation_key",
        },
        "references": references,
    }


def attach_citation_layer(
    payload: dict[str, Any],
    citations: Iterable[Any] | None,
) -> dict[str, Any]:
    """Add citation presentation fields without risking the primary payload."""
    try:
        layer = build_citation_layer(citations or [])
        if not layer["references"]:
            return payload

        enriched = dict(payload)
        enriched["citation_layer"] = layer
        return enriched
    except Exception:
        return payload


def citations_from_rows(rows: Iterable[Any]) -> list[Any]:
    citations: list[Any] = []
    for row in rows:
        try:
            row_citations = _raw_field(row, "citations") or []
            if isinstance(row_citations, list | tuple):
                citations.extend(row_citations)
            else:
                citations.append(row_citations)
        except Exception:
            continue
    return citations


def _raw_field(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _field(citation: Any, name: str) -> Any:
    value = _raw_field(citation, name)
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    return compact_whitespace(value)


def _short_label(
    source: str,
    title: str | None,
    citation_id: str | None,
    url: str | None,
) -> str:
    label = title or citation_id or url or source
    label = compact_whitespace(label) or source
    return label if len(label) <= 96 else f"{label[:93]}..."


def _hover_card(
    source: str,
    title: str | None,
    citation_id: str | None,
    url: str | None,
    label: str,
) -> dict[str, str | None]:
    display_url = _display_url(url)
    subtitle = " - ".join(part for part in [source, citation_id] if part)
    tooltip_parts = [label, subtitle, display_url]
    tooltip = "\n".join(part for part in tooltip_parts if part)

    return {
        "title": label,
        "source": source,
        "id": citation_id,
        "url": url,
        "display_url": display_url,
        "subtitle": subtitle or None,
        "tooltip": tooltip,
    }


def _display_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if not parsed.netloc:
        return url
    path = parsed.path.rstrip("/")
    return f"{parsed.netloc}{path}" if path else parsed.netloc

