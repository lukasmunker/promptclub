"""Inline Markdown recipe: target-disease associations from Open Targets.

Renders as a ``text/markdown`` envelope — a GFM table showing which protein
targets are associated with a given disease, with the association score
visualized as a Unicode block-character bar (``████████░░``) so it appears
inline in the chat bubble without needing the artifact pane.

Works on the normalized shape produced by ``app.viz.adapters._normalize_target_associations``::

    {
        "disease_id": "EFO_0000756",
        "disease_name": "melanoma",
        "associations": [
            {
                "target_symbol": "BRAF",
                "target_name": "B-Raf proto-oncogene",
                "target_id": "ENSG00000157764",
                "score": 0.92
            }
        ]
    }
"""

from __future__ import annotations

from typing import Any

from app.viz.contract import ArtifactMeta, UiPayload
from app.viz.utils.citations import format_source_footer
from app.viz.utils.identifiers import make_identifier

__all__ = ["build", "MAX_ROWS", "BAR_WIDTH"]

MAX_ROWS = 20
BAR_WIDTH = 10  # Each bar is 10 characters wide (0.0 → 1.0 scaled)


def build(
    data: dict[str, Any],
    sources: list[Any] | None = None,
) -> UiPayload:
    disease_name = data.get("disease_name") or "Disease"
    disease_id = data.get("disease_id") or "unknown"
    title = f"Target Associations — {disease_name}"

    associations = data.get("associations") or []
    # Sort by score descending, then take top N
    associations_sorted = sorted(
        associations,
        key=lambda a: a.get("score") or 0,
        reverse=True,
    )[:MAX_ROWS]

    rows_md = "\n".join(_row(a) for a in associations_sorted)

    opentargets_url = f"https://platform.opentargets.org/disease/{disease_id}"

    # Always show the disease-specific Open Targets context line — this is
    # recipe-specific info (the EFO ID) that doesn't fit the generic footer.
    # The generic source footer (counts + retrieved_at) is appended below.
    disease_context = (
        f"_Disease ID `{_md_escape_cell(disease_id)}` · "
        f"[view on Open Targets]({_md_escape_url(opentargets_url)})_\n\n"
    )

    source_footer = format_source_footer(sources)

    raw = (
        f"## {_md_escape(title)}\n\n"
        f"{disease_context}"
        f"| Target | Name | Score |\n"
        f"| --- | --- | --- |\n"
        f"{rows_md}\n"
        f"{source_footer}"
    )

    return UiPayload(
        recipe="target_associations_table",
        artifact=ArtifactMeta(
            identifier=make_identifier("target_associations_table", disease_id),
            type="text/markdown",
            title=title,
        ),
        components=None,
        layout=None,
        blueprint=None,
        raw=raw,
    )


# --- Row rendering ---------------------------------------------------------


def _row(assoc: dict[str, Any]) -> str:
    symbol = assoc.get("target_symbol") or "?"
    name = assoc.get("target_name") or ""
    target_id = assoc.get("target_id") or ""
    score = assoc.get("score")

    # Symbol cell: linked to Open Targets if we have a target_id
    if target_id:
        symbol_cell = (
            f"[`{_md_escape_cell(symbol)}`]"
            f"(https://platform.opentargets.org/target/{_md_escape_url(target_id)})"
        )
    else:
        symbol_cell = f"`{_md_escape_cell(symbol)}`"

    name_cell = _md_escape_cell(_truncate(name, 60)) or "—"

    # Score cell: ASCII bar + numeric value
    if isinstance(score, (int, float)):
        clamped = max(0.0, min(1.0, float(score)))
        filled = round(clamped * BAR_WIDTH)
        bar = "█" * filled + "░" * (BAR_WIDTH - filled)
        score_cell = f"`{bar}` {clamped:.2f}"
    else:
        score_cell = "—"

    return f"| {symbol_cell} | {name_cell} | {score_cell} |"


# --- Escaping helpers ------------------------------------------------------


def _md_escape(text: object) -> str:
    if text is None:
        return ""
    s = str(text)
    return s.replace("\\", "\\\\").replace("_", "\\_").replace("*", "\\*")


def _md_escape_cell(text: object) -> str:
    if text is None:
        return ""
    s = str(text).replace("\n", " ").replace("\r", " ").strip()
    return s.replace("|", "\\|")


def _md_escape_url(url: object) -> str:
    if url is None:
        return ""
    return str(url).replace(")", "%29").replace("(", "%28").replace(" ", "%20")


def _truncate(text: str | None, max_len: int) -> str:
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"
