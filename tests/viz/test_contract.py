"""Tests for the Pydantic envelope contract."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.viz.contract import (
    ArtifactMeta,
    BlueprintNode,
    ComponentImport,
    Envelope,
    Source,
    UiPayload,
)
from app.viz.render_hints import HTML as HTML_HINT
from app.viz.render_hints import MERMAID as MERMAID_HINT
from app.viz.render_hints import SKIP as SKIP_HINT


# --- Source -----------------------------------------------------------------


def test_source_accepts_all_kinds():
    for kind in ("clinicaltrials.gov", "pubmed", "openfda", "opentargets", "web"):
        Source(
            kind=kind,
            id="x",
            url="https://example.com/x",
            retrieved_at=datetime.now(timezone.utc),
        )


def test_source_rejects_unknown_kind():
    with pytest.raises(ValueError):
        Source(
            kind="patents",  # forbidden — never a patent source
            id="x",
            url="https://example.com/x",
            retrieved_at=datetime.now(timezone.utc),
        )


# --- ComponentImport (legacy type, retained for back-compat) ----------------
# ``ComponentImport`` / ``BlueprintNode`` are no longer used by any recipe —
# all artifacts are now ``text/html`` or ``application/vnd.mermaid`` with a
# ``raw`` string. The classes are kept in the contract for forward-compat in
# case a future recipe wants the React-blueprint path back.


def test_component_import_accepts_shadcn_path():
    ci = ComponentImport(**{"from": "/components/ui/card", "import": ["Card"]})
    assert ci.from_ == "/components/ui/card"
    assert ci.imports == ["Card"]


def test_component_import_accepts_recharts():
    ComponentImport(**{"from": "recharts", "import": ["BarChart"]})


def test_component_import_accepts_lucide_react():
    ComponentImport(**{"from": "lucide-react", "import": ["Activity"]})


def test_component_import_rejects_scoped_shadcn_path():
    with pytest.raises(ValueError, match="Invalid import source"):
        ComponentImport(**{"from": "@/components/ui/card", "import": ["Card"]})


def test_component_import_rejects_arbitrary_package():
    with pytest.raises(ValueError, match="Invalid import source"):
        ComponentImport(**{"from": "framer-motion", "import": ["motion"]})


def test_component_import_requires_non_empty_list():
    with pytest.raises(ValueError):
        ComponentImport(**{"from": "recharts", "import": []})


# --- UiPayload shape validation --------------------------------------------


def _html_payload_kwargs():
    return dict(
        recipe="trial_search_results",
        artifact=ArtifactMeta(
            identifier="trial_search_results-x-2026-04-09",
            type="text/html",
            title="X",
        ),
        raw="<div>hello</div>",
    )


def _mermaid_payload_kwargs():
    return dict(
        recipe="trial_timeline_gantt",
        artifact=ArtifactMeta(
            identifier="trial_timeline_gantt-x-2026-04-09",
            type="application/vnd.mermaid",
            title="X",
        ),
        raw="gantt\n    dateFormat YYYY-MM-DD",
    )


def test_html_payload_requires_raw():
    kwargs = _html_payload_kwargs()
    kwargs["raw"] = ""
    with pytest.raises(ValueError, match="non-empty"):
        UiPayload(**kwargs)


def test_html_payload_rejects_blueprint():
    kwargs = _html_payload_kwargs()
    kwargs["blueprint"] = [BlueprintNode(component="div")]
    with pytest.raises(ValueError, match="must not populate `blueprint`"):
        UiPayload(**kwargs)


def test_html_payload_rejects_components():
    kwargs = _html_payload_kwargs()
    kwargs["components"] = [
        ComponentImport(**{"from": "recharts", "import": ["BarChart"]})
    ]
    with pytest.raises(ValueError, match="must not populate `components`"):
        UiPayload(**kwargs)


def test_mermaid_payload_requires_raw():
    kwargs = _mermaid_payload_kwargs()
    kwargs["raw"] = "   "
    with pytest.raises(ValueError, match="non-empty"):
        UiPayload(**kwargs)


def test_mermaid_payload_rejects_blueprint():
    kwargs = _mermaid_payload_kwargs()
    kwargs["blueprint"] = [BlueprintNode(component="div")]
    with pytest.raises(ValueError, match="must not populate `blueprint`"):
        UiPayload(**kwargs)


def test_artifact_type_rejects_legacy_react_type():
    """application/vnd.react was removed from the ArtifactType literal after
    the Sandpack crash fix. Sanity-check that it no longer validates."""
    with pytest.raises(ValueError):
        ArtifactMeta(
            identifier="x",
            type="application/vnd.react",  # no longer allowed
            title="X",
        )


def test_artifact_type_rejects_text_markdown():
    """text/markdown was an interim inline-markdown type used between
    dcc87d3 and the artifact restoration. No longer allowed."""
    with pytest.raises(ValueError):
        ArtifactMeta(
            identifier="x",
            type="text/markdown",
            title="X",
        )


# --- Envelope + render_hint compliance --------------------------------------


def test_envelope_with_ui_validates():
    ui = UiPayload(**_html_payload_kwargs())
    env = Envelope(render_hint=HTML_HINT, ui=ui, data={"results": []})
    assert env.ui is not None
    assert env.sources == []


def test_envelope_without_ui_validates():
    env = Envelope(render_hint=SKIP_HINT, ui=None, data={"message": "no data"})
    assert env.ui is None


def test_render_hint_must_mention_sources():
    bad_hint = "Render this as HTML. No forward-looking statements."
    with pytest.raises(ValueError, match="Cite sources"):
        Envelope(render_hint=bad_hint, data={})


def test_render_hint_must_mention_no_forward_looking():
    bad_hint = "Render this as HTML. Cite sources from the sources field."
    with pytest.raises(ValueError, match="No forward-looking"):
        Envelope(render_hint=bad_hint, data={})


def test_all_builtin_hints_pass_compliance():
    for hint in (HTML_HINT, MERMAID_HINT, SKIP_HINT):
        # Should not raise
        Envelope(render_hint=hint, data={})
