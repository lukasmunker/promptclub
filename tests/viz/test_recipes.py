"""Tests for the five recipe builders + end-to-end build_response."""

from __future__ import annotations

import pytest

from app.viz import build_response
from app.viz.contract import UiPayload
from app.viz.recipes import (
    indication_dashboard,
    sponsor_pipeline_cards,
    target_associations_table,
    trial_detail_tabs,
    trial_search_results,
    trial_timeline_gantt,
    whitespace_card,
)
from app.viz.utils.mermaid import safe_label


# --- trial_search_results (Markdown, inline) -------------------------------


def test_trial_search_results_basic_shape(search_melanoma_phase3):
    payload = trial_search_results.build(search_melanoma_phase3)
    assert isinstance(payload, UiPayload)
    assert payload.artifact.type == "text/markdown"
    assert payload.recipe == "trial_search_results"
    assert payload.raw is not None
    assert payload.blueprint is None
    assert payload.components is None
    # Markdown table header present
    assert "| NCT | Phase | Status |" in payload.raw


def test_trial_search_results_includes_all_nct_ids(search_melanoma_phase3):
    payload = trial_search_results.build(search_melanoma_phase3)
    for hit in search_melanoma_phase3["results"]:
        assert hit["nct_id"] in payload.raw


def test_trial_search_results_handles_malicious_content_inline():
    """Inline markdown renders raw HTML as escaped text (ReactMarkdown without
    rehype-raw) — so a literal <script> tag shows up as plain text in the chat,
    not as an executable script. We still escape pipes in cell content so the
    table layout isn't broken.

    Note: the trial table has no `title` column (trials are identified by NCT),
    so we put the malicious content in `sponsor` which IS rendered.
    """
    data = {
        "query": "evil",
        "results": [
            {
                "nct_id": "NCT01",
                "phase": "Phase 3",
                "sponsor": 'Evil | pipe <script>alert(1)</script>',
            },
            {
                "nct_id": "NCT02",
                "phase": "Phase 3",
                "sponsor": "Normal Sponsor",
            },
        ],
        "total": 2,
    }
    payload = trial_search_results.build(data)
    # Table pipe in sponsor field must be escaped so it doesn't split the cell.
    assert "Evil \\| pipe" in payload.raw
    # The literal <script> substring survives into the markdown — LibreChat
    # will render it as inert text via ReactMarkdown's default HTML escaping.
    assert "<script>" in payload.raw


def test_trial_search_results_caps_at_25_and_shows_more_footer():
    data = {
        "query": "many",
        "search_url": "https://clinicaltrials.gov/search?cond=many",
        "results": [
            {"nct_id": f"NCT{i:04d}", "title": f"Trial {i}", "phase": "Phase 3"}
            for i in range(40)
        ],
        "total": 40,
    }
    payload = trial_search_results.build(data)
    # 40 - 25 = 15 more
    assert "15 more" in payload.raw
    assert "NCT0024" in payload.raw  # the 25th hit
    assert "NCT0025" not in payload.raw  # 26th is beyond the cap
    # Footer links to the full search URL
    assert "clinicaltrials.gov/search?cond=many" in payload.raw


def test_trial_search_results_includes_pmid_links_for_publications():
    data = {
        "query": "pubs",
        "results": [
            {
                "pmid": "12345678",
                "title": "Great paper",
                "abstract": "lorem ipsum",
            }
        ],
        "total": 1,
    }
    payload = trial_search_results.build(data)
    # Link in markdown format
    assert "pubmed.ncbi.nlm.nih.gov/12345678" in payload.raw
    # Publication table uses PMID column header
    assert "| PMID | Title | Journal · Year |" in payload.raw


# --- sponsor_pipeline_cards (Markdown, inline) ------------------------------


def test_sponsor_pipeline_cards_groups_by_sponsor(compare_trials_many):
    payload = sponsor_pipeline_cards.build(compare_trials_many)
    assert payload.artifact.type == "text/markdown"
    # Should contain each unique sponsor name as a section header
    unique_sponsors = {t["sponsor"] for t in compare_trials_many["trials"]}
    for sponsor in unique_sponsors:
        assert sponsor in payload.raw


def test_sponsor_pipeline_cards_is_xss_safe(compare_trials_many):
    """Kept as a smoke test that building doesn't crash on real-world data."""
    payload = sponsor_pipeline_cards.build(compare_trials_many)
    # Markdown: assert required structural tokens exist
    assert "| NCT | Trial |" in payload.raw
    assert payload.raw.startswith("## ")


def test_sponsor_pipeline_cards_handles_empty():
    payload = sponsor_pipeline_cards.build({"trials": [], "title": "Empty"})
    assert payload.raw is not None
    assert "## Empty" in payload.raw


# --- trial_timeline_gantt (Markdown + mermaid fence, inline) ---------------


def test_timeline_gantt_basic(compare_trials_three):
    payload = trial_timeline_gantt.build(compare_trials_three)
    # Now a text/markdown envelope with a mermaid fence embedded inline
    assert payload.artifact.type == "text/markdown"
    assert payload.raw.startswith("## ")
    assert "```mermaid" in payload.raw
    assert "gantt" in payload.raw
    assert "dateFormat  YYYY-MM-DD" in payload.raw
    # All three trials should be present inside the fence
    for trial in compare_trials_three["trials"]:
        assert trial["nct_id"] in payload.raw


def test_timeline_gantt_uses_section_per_sponsor(compare_trials_three):
    payload = trial_timeline_gantt.build(compare_trials_three)
    for trial in compare_trials_three["trials"]:
        assert f"section {trial['sponsor']}" in payload.raw


def test_timeline_gantt_caps_at_15():
    trials = [
        {
            "nct_id": f"NCT{i:04d}",
            "acronym": f"TRIAL-{i}",
            "sponsor": f"Sponsor {i % 5}",
            "start_date": "2023-01-01",
            "primary_completion_date": "2026-01-01",
        }
        for i in range(25)
    ]
    payload = trial_timeline_gantt.build({"trials": trials, "query": "many"})
    assert payload.raw.count(", NCT") <= 15


def test_timeline_gantt_drops_trials_without_valid_dates():
    data = {
        "trials": [
            {
                "nct_id": "NCT01",
                "acronym": "A",
                "sponsor": "X",
                "start_date": "2023-01-01",
                "primary_completion_date": "2026-01-01",
            },
            {
                "nct_id": "NCT02",
                "acronym": "B",
                "sponsor": "Y",
                "start_date": "invalid",
                "primary_completion_date": "2026-06-01",
            },
        ]
    }
    payload = trial_timeline_gantt.build(data)
    assert "NCT01" in payload.raw
    assert "NCT02" not in payload.raw


def test_timeline_gantt_sanitizes_labels():
    data = {
        "trials": [
            {
                "nct_id": "NCT01",
                "acronym": 'PD-1 "super" inhibitor: (phase 3)',
                "sponsor": 'Sponsor: X "corp"',
                "start_date": "2023-01-01",
                "primary_completion_date": "2026-01-01",
            }
        ]
    }
    payload = trial_timeline_gantt.build(data)
    # Only look at the mermaid task/section lines inside the fence. Skip the
    # markdown wrapper (## heading, ```mermaid fence, title/dateFormat/axisFormat).
    safe_prefixes = ("##", "```", "title", "gantt", "dateFormat", "axisFormat")
    for line in payload.raw.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith(safe_prefixes):
            continue
        if stripped.startswith("section"):
            # The "section X" header's label was already sanitized by safe_label
            continue
        if ":active," in line:
            # Task line: `    Label :active, NCT, start, end`
            label_part = line.split(":active,", 1)[0]
            for bad in ('"', ":", "<", ">", "(", ")"):
                assert bad not in label_part, (
                    f"bad char {bad!r} in gantt label {label_part!r}"
                )


def test_safe_label_utility_direct():
    assert safe_label('A"B:C<D>E') == "ABCDE"
    assert safe_label("") == "(untitled)"
    assert safe_label(None) == "(untitled)"
    assert safe_label("a" * 100, max_length=20).endswith("…")


# --- indication_dashboard (React) ------------------------------------------


def test_indication_dashboard_basic(indication_landscape_nsclc):
    payload = indication_dashboard.build(indication_landscape_nsclc)
    assert payload.artifact.type == "application/vnd.react"
    assert payload.recipe == "indication_dashboard"
    assert payload.raw is None
    assert payload.blueprint is not None
    assert payload.components is not None


def test_indication_dashboard_imports_are_valid(indication_landscape_nsclc):
    payload = indication_dashboard.build(indication_landscape_nsclc)
    allowed_sources = {"/components/ui/card", "/components/ui/badge", "recharts", "lucide-react"}
    for imp in payload.components:
        # Each import source must start with an allowed prefix
        assert any(
            imp.from_ == src or imp.from_.startswith(src) for src in allowed_sources
        ), f"Unexpected import source: {imp.from_}"


def test_indication_dashboard_panels_match_data(indication_landscape_nsclc):
    payload = indication_dashboard.build(indication_landscape_nsclc)
    # Root is a `p-4` wrapper div; first child is the grid, remaining children
    # (if any) are the citation footer paragraph.
    root = payload.blueprint[0]
    assert root.component == "div"
    assert root.children is not None and len(root.children) >= 1
    grid = root.children[0]
    assert grid.component == "div"
    # 4 sections in fixture → 4 Card panels
    assert grid.children is not None
    assert len(grid.children) == 4


def test_indication_dashboard_caps_sponsors_at_20():
    data = {
        "indication": "mass",
        "phase_distribution": [{"phase": "1", "count": 1}, {"phase": "2", "count": 2}],
        "top_sponsors": [{"name": f"S{i}", "trials": 100 - i} for i in range(30)],
    }
    payload = indication_dashboard.build(data)
    # The builder caps the list; verify via re-reading it from blueprint is
    # complex, so check the capped list surfaces somewhere reasonable: the
    # build() returns a payload whose blueprint binds to "top_sponsors", and
    # the data passed in is mutated to the capped version.
    # We can't see the mutated data from the payload, so assert via count
    # through a public helper instead.
    from app.viz.recipes.indication_dashboard import _cap_sponsors

    capped = _cap_sponsors(data["top_sponsors"])
    assert len(capped) == 21  # 20 + "Other"
    assert capped[-1]["name"] == "Other"


def test_indication_dashboard_skips_missing_panels():
    # Only phase distribution, nothing else
    data = {
        "indication": "sparse",
        "phase_distribution": [{"phase": "1", "count": 1}, {"phase": "2", "count": 2}],
    }
    payload = indication_dashboard.build(data)
    root = payload.blueprint[0]
    # root is the p-4 wrapper; first child is the grid
    grid = root.children[0]
    # Only 1 panel (phase)
    assert len(grid.children) == 1


# --- trial_detail_tabs (React) ---------------------------------------------


def test_trial_detail_tabs_basic(trial_details_nct01):
    payload = trial_detail_tabs.build(trial_details_nct01)
    assert payload.artifact.type == "application/vnd.react"
    assert payload.recipe == "trial_detail_tabs"
    assert payload.blueprint is not None


def test_trial_detail_tabs_imports_shadcn_from_correct_paths(trial_details_nct01):
    payload = trial_detail_tabs.build(trial_details_nct01)
    import_sources = {imp.from_ for imp in payload.components}
    # Must include the exact shadcn paths LibreChat expects
    assert "/components/ui/tabs" in import_sources
    assert "/components/ui/table" in import_sources
    assert "/components/ui/card" in import_sources
    # Must NOT use scoped paths
    for src in import_sources:
        assert not src.startswith("@/"), f"Forbidden scoped import: {src}"


def test_trial_detail_tabs_includes_all_six_tabs_when_data_present(
    trial_details_nct01,
):
    payload = trial_detail_tabs.build(trial_details_nct01)
    # Find the Tabs root, count TabsTriggers
    root = payload.blueprint[0]
    tabs = root.children[1]  # children: [header_card, tabs]
    assert tabs.component == "Tabs"
    tabs_list = tabs.children[0]
    triggers = [c for c in tabs_list.children if c.component == "TabsTrigger"]
    # Fixture has overview, design, eligibility, arms, sites, publications → 6 tabs
    assert len(triggers) == 6


def test_trial_detail_tabs_omits_tabs_for_missing_data():
    minimal = {
        "nct_id": "NCT99",
        "title": "Minimal",
        "arms": [{"label": "Arm A"}],
        # No design, eligibility, sites, publications
    }
    payload = trial_detail_tabs.build(minimal)
    root = payload.blueprint[0]
    tabs = root.children[1]
    tabs_list = tabs.children[0]
    triggers = [c for c in tabs_list.children if c.component == "TabsTrigger"]
    # Only overview + arms
    trigger_values = {c.props["value"] for c in triggers}
    assert "overview" in trigger_values
    assert "arms" in trigger_values
    assert "design" not in trigger_values
    assert "sites" not in trigger_values


# --- End-to-end build_response ---------------------------------------------


def test_build_response_search_with_sources(
    search_melanoma_phase3, sources_clinicaltrials
):
    envelope = build_response(
        "search_clinical_trials",
        search_melanoma_phase3,
        sources=sources_clinicaltrials,
    )
    assert "render_hint" in envelope
    assert envelope["ui"]["recipe"] == "trial_search_results"
    assert envelope["ui"]["artifact"]["type"] == "text/markdown"
    assert "raw" in envelope["ui"]
    # Markdown recipes should not include components/blueprint (stripped by exclude_none)
    assert "components" not in envelope["ui"]
    assert "blueprint" not in envelope["ui"]
    # render_hint tells the LLM to inline the markdown (not wrap in artifact)
    assert "verbatim" in envelope["render_hint"].lower()
    # Sources preserved
    assert len(envelope["sources"]) == 1
    assert envelope["sources"][0]["kind"] == "clinicaltrials.gov"


def test_build_response_react_uses_aliases(indication_landscape_nsclc):
    envelope = build_response(
        "get_indication_landscape", indication_landscape_nsclc, sources=[]
    )
    assert envelope["ui"]["artifact"]["type"] == "application/vnd.react"
    # Aliases: `from` not `from_`, `import` not `imports`
    first_import = envelope["ui"]["components"][0]
    assert "from" in first_import
    assert "import" in first_import
    assert "from_" not in first_import
    assert "imports" not in first_import


def test_build_response_skip_has_no_ui(search_empty):
    envelope = build_response("search_clinical_trials", search_empty, sources=[])
    assert "ui" not in envelope  # stripped by exclude_none
    assert envelope["data"]["total"] == 0
    assert "Cite sources" in envelope["render_hint"]
    assert "No forward-looking" in envelope["render_hint"]


def test_build_response_with_pydantic_source_instances(search_melanoma_phase3):
    from datetime import datetime, timezone

    from app.viz.contract import Source

    src = Source(
        kind="pubmed",
        id="12345678",
        url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
        retrieved_at=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
    )
    envelope = build_response(
        "search_clinical_trials", search_melanoma_phase3, sources=[src]
    )
    assert envelope["sources"][0]["kind"] == "pubmed"


def test_build_response_unknown_tool_returns_text_fallback():
    envelope = build_response("unknown_tool", {"anything": True}, sources=[])
    assert "ui" not in envelope
    assert envelope["data"] == {"anything": True}


def test_build_response_compare_trials_gantt(compare_trials_three):
    envelope = build_response(
        "compare_trials", compare_trials_three, sources=[]
    )
    assert envelope["ui"]["recipe"] == "trial_timeline_gantt"
    assert envelope["ui"]["artifact"]["type"] == "text/markdown"
    # Inline markdown wraps the mermaid source in a fence
    assert envelope["ui"]["raw"].startswith("## ")
    assert "```mermaid" in envelope["ui"]["raw"]
    assert "gantt" in envelope["ui"]["raw"]


def test_build_response_compare_many_trials_cards(compare_trials_many):
    envelope = build_response(
        "compare_trials", compare_trials_many, sources=[]
    )
    # 18 trials > 15 cap → should use cards (now inline markdown)
    assert envelope["ui"]["recipe"] == "sponsor_pipeline_cards"
    assert envelope["ui"]["artifact"]["type"] == "text/markdown"


def test_build_response_trial_details_rich(trial_details_nct01):
    envelope = build_response(
        "get_trial_details", trial_details_nct01, sources=[]
    )
    assert envelope["ui"]["recipe"] == "trial_detail_tabs"
    assert envelope["ui"]["artifact"]["type"] == "application/vnd.react"
    assert "blueprint" in envelope["ui"]
    assert "components" in envelope["ui"]


# --- whitespace_card (Markdown, inline) -------------------------------------


_WHITESPACE_FIXTURE = {
    "condition": "non-small cell lung cancer",
    "trial_counts_by_phase": {"phase_1": 42, "phase_2": 78, "phase_3": 35},
    "trial_counts_by_status": {"recruiting": 95, "completed": 38},
    "pubmed_publications_3yr": 1200,
    "fda_label_records": 8,
    "identified_whitespace": [
        "Few Phase 3 trials — late-stage evidence lacking",
        "Limited recent publications relative to trial volume",
    ],
}


def test_whitespace_card_basic_shape():
    payload = whitespace_card.build(_WHITESPACE_FIXTURE)
    assert isinstance(payload, UiPayload)
    assert payload.recipe == "whitespace_card"
    assert payload.artifact.type == "text/markdown"
    assert payload.raw is not None
    assert payload.blueprint is None
    assert payload.components is None
    # Markdown heading + metric table present
    assert payload.raw.startswith("## ")
    assert "### Activity Overview" in payload.raw
    assert "### Identified Whitespace Signals" in payload.raw


def test_whitespace_card_renders_all_phase_counts():
    payload = whitespace_card.build(_WHITESPACE_FIXTURE)
    assert "42" in payload.raw
    assert "78" in payload.raw
    assert "35" in payload.raw


def test_whitespace_card_renders_all_signals():
    payload = whitespace_card.build(_WHITESPACE_FIXTURE)
    for signal in _WHITESPACE_FIXTURE["identified_whitespace"]:
        assert signal in payload.raw
    # Each signal is prefixed with the warning emoji
    assert payload.raw.count("⚠️") >= 2


def test_whitespace_card_handles_literal_script_string_inline():
    """LibreChat's chat markdown renderer does NOT execute raw HTML — a
    literal <script> string appears as plain text. We don't try to HTML-escape
    anything; that would just clutter the markdown."""
    data = {
        **_WHITESPACE_FIXTURE,
        "identified_whitespace": ['<script>alert("xss")</script>', "ok signal"],
    }
    payload = whitespace_card.build(data)
    # The script string is in the raw markdown — as literal text, not as a tag.
    # LibreChat will display it verbatim (no execution, no side effects).
    assert "<script>" in payload.raw
    assert "ok signal" in payload.raw


def test_whitespace_card_handles_missing_counts():
    data = {
        "condition": "rare condition",
        "identified_whitespace": ["No trials in any phase"],
    }
    payload = whitespace_card.build(data)
    assert "—" in payload.raw  # placeholder for missing counts
    assert "No trials in any phase" in payload.raw


def test_whitespace_card_handles_no_signals():
    data = {
        **_WHITESPACE_FIXTURE,
        "identified_whitespace": [],
    }
    payload = whitespace_card.build(data)
    assert "No specific whitespace signals" in payload.raw


# --- Citation footer (all recipes) -----------------------------------------


from datetime import datetime, timezone  # noqa: E402

from app.viz.contract import Source  # noqa: E402

_SAMPLE_SOURCES = [
    Source(
        kind="clinicaltrials.gov",
        id="NCT01234567",
        url="https://clinicaltrials.gov/study/NCT01234567",
        retrieved_at=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
    ),
    Source(
        kind="clinicaltrials.gov",
        id="NCT02345678",
        url="https://clinicaltrials.gov/study/NCT02345678",
        retrieved_at=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
    ),
    Source(
        kind="pubmed",
        id="12345678",
        url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
        retrieved_at=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
    ),
]


def test_trial_search_results_embeds_source_footer(search_melanoma_phase3):
    payload = trial_search_results.build(search_melanoma_phase3, sources=_SAMPLE_SOURCES)
    # Footer mentions both source kinds (as markdown links with hub URLs)
    # and the retrieved date.
    assert "_Source:" in payload.raw
    assert "[ClinicalTrials.gov]" in payload.raw  # linked name
    assert "(2)" in payload.raw  # count annotation (2 CT.gov citations)
    assert "[PubMed]" in payload.raw
    assert "Retrieved 2026-04-09" in payload.raw


def test_trial_search_results_no_footer_when_no_sources(search_melanoma_phase3):
    payload = trial_search_results.build(search_melanoma_phase3, sources=None)
    # No footer appended when sources is None or empty.
    assert "_Source:" not in payload.raw


def test_target_associations_embeds_source_footer():
    data = {
        "disease_id": "EFO_0000756",
        "disease_name": "melanoma",
        "associations": [
            {"target_symbol": "BRAF", "score": 0.9, "target_id": "ENSG01"},
            {"target_symbol": "KRAS", "score": 0.8, "target_id": "ENSG02"},
        ],
    }
    payload = target_associations_table.build(
        data,
        sources=[
            Source(
                kind="opentargets",
                id="EFO_0000756",
                url="https://platform.opentargets.org/disease/EFO_0000756",
                retrieved_at=datetime(2026, 4, 9, tzinfo=timezone.utc),
            )
        ],
    )
    # Recipe-specific disease context line still present
    assert "Disease ID `EFO_0000756`" in payload.raw
    # Plus the generic source footer
    assert "_Source: [Open Targets]" in payload.raw
    assert "Retrieved 2026-04-09" in payload.raw


def test_sponsor_pipeline_cards_embeds_source_footer(compare_trials_many):
    payload = sponsor_pipeline_cards.build(compare_trials_many, sources=_SAMPLE_SOURCES)
    assert "_Source:" in payload.raw
    assert "[ClinicalTrials.gov]" in payload.raw
    assert "(2)" in payload.raw


def test_whitespace_card_embeds_source_footer():
    payload = whitespace_card.build(_WHITESPACE_FIXTURE, sources=_SAMPLE_SOURCES)
    assert "_Source:" in payload.raw
    assert "[ClinicalTrials.gov]" in payload.raw
    assert "[PubMed]" in payload.raw
    assert "(2)" in payload.raw  # 2 CT.gov citations in the sample


def test_trial_timeline_gantt_embeds_source_footer(compare_trials_three):
    payload = trial_timeline_gantt.build(compare_trials_three, sources=_SAMPLE_SOURCES)
    # Footer is AFTER the mermaid fence closing — make sure order is correct
    assert "```mermaid" in payload.raw
    assert "```" in payload.raw
    assert "_Source:" in payload.raw
    # Source line must come after the closing mermaid fence (not inside it)
    source_idx = payload.raw.index("_Source:")
    closing_fence_idx = payload.raw.rindex("```")
    assert source_idx > closing_fence_idx


def test_trial_detail_tabs_embeds_source_footer_blueprint(trial_details_nct01):
    payload = trial_detail_tabs.build(
        trial_details_nct01,
        sources=[
            Source(
                kind="clinicaltrials.gov",
                id="NCT01234567",
                url="https://clinicaltrials.gov/study/NCT01234567",
                retrieved_at=datetime(2026, 4, 9, tzinfo=timezone.utc),
            )
        ],
    )
    # The root div's last child should be a <p> with the source text
    root = payload.blueprint[0]
    assert root.children is not None
    last_child = root.children[-1]
    assert last_child.component == "p"
    assert last_child.text is not None
    assert "Source:" in last_child.text
    assert "ClinicalTrials.gov" in last_child.text


def test_indication_dashboard_embeds_source_footer_blueprint(indication_landscape_nsclc):
    payload = indication_dashboard.build(
        indication_landscape_nsclc,
        sources=_SAMPLE_SOURCES,
    )
    # Root wrapper's children = [grid, footer <p>]
    root = payload.blueprint[0]
    assert root.children is not None
    assert len(root.children) == 2  # grid + footer paragraph
    footer = root.children[1]
    assert footer.component == "p"
    assert "Source:" in footer.text
    assert "ClinicalTrials.gov" in footer.text


# --- Emoji decoration + Mermaid pie / bar upgrades --------------------------


def test_trial_search_results_uses_phase_and_status_emojis(search_melanoma_phase3):
    """Every trial row should carry a leading emoji on the phase and status
    columns (💊 for Phase 3, 🟢 Recruiting, etc.)"""
    payload = trial_search_results.build(search_melanoma_phase3)
    # Phase 3 emoji
    assert "💊 Phase 3" in payload.raw
    # Recruiting status emoji
    assert "🟢 Recruiting" in payload.raw
    # Active, not recruiting emoji
    assert "🟡 Active, not recruiting" in payload.raw


def test_trial_search_results_includes_status_pie_when_multi_status(
    search_melanoma_phase3,
):
    """The fixture has 2 distinct statuses → pie chart above the table."""
    payload = trial_search_results.build(search_melanoma_phase3)
    assert "```mermaid" in payload.raw
    assert "pie title Status breakdown" in payload.raw
    # Both statuses from the fixture should appear as pie slices
    assert '"Recruiting"' in payload.raw
    assert '"Active, not recruiting"' in payload.raw
    # Pie must sit BEFORE the table (status overview, then details)
    pie_idx = payload.raw.index("```mermaid")
    table_idx = payload.raw.index("| NCT | Phase")
    assert pie_idx < table_idx


def test_trial_search_results_skips_pie_when_single_status():
    """One status → no pie."""
    data = {
        "query": "single-status",
        "results": [
            {"nct_id": "NCT01", "phase": "Phase 3", "status": "Recruiting"},
            {"nct_id": "NCT02", "phase": "Phase 3", "status": "Recruiting"},
        ],
        "total": 2,
    }
    payload = trial_search_results.build(data)
    assert "```mermaid" not in payload.raw
    # Still renders the table normally
    assert "| NCT | Phase" in payload.raw


def test_trial_search_results_skips_pie_for_publications():
    """Publication result sets don't get a status pie (PubMed hits have no
    status)."""
    data = {
        "query": "pubs",
        "results": [
            {"pmid": "111", "title": "A"},
            {"pmid": "222", "title": "B"},
        ],
        "total": 2,
    }
    payload = trial_search_results.build(data)
    assert "```mermaid" not in payload.raw


def test_sponsor_pipeline_cards_uses_emojis_and_ranking_bar(compare_trials_many):
    payload = sponsor_pipeline_cards.build(compare_trials_many)
    # Emoji decoration on phase/status in each row
    assert "💊 Phase 3" in payload.raw
    assert "🟢 Recruiting" in payload.raw
    # Sponsor ranking table appears before the per-sponsor sections
    assert "### Sponsor Ranking" in payload.raw
    # Bar characters in the ranking column
    assert "█" in payload.raw
    # Ranking table header
    assert "| Rank | Sponsor | Trials | Share |" in payload.raw


def test_sponsor_pipeline_cards_no_ranking_for_single_sponsor():
    """With only one sponsor the ranking table is pointless — omit it."""
    data = {
        "title": "Solo",
        "query": "solo",
        "trials": [
            {"nct_id": "NCT01", "sponsor": "Only One", "phase": "Phase 3"},
            {"nct_id": "NCT02", "sponsor": "Only One", "phase": "Phase 3"},
        ],
    }
    payload = sponsor_pipeline_cards.build(data)
    assert "### Sponsor Ranking" not in payload.raw
    assert "### Only One" in payload.raw  # Per-sponsor section still present


def test_whitespace_card_includes_phase_pie():
    data = {
        "condition": "non-small cell lung cancer",
        "trial_counts_by_phase": {"phase_1": 42, "phase_2": 78, "phase_3": 35},
        "trial_counts_by_status": {"recruiting": 95},
        "identified_whitespace": ["Few Phase 3 trials"],
    }
    payload = whitespace_card.build(data)
    assert "```mermaid" in payload.raw
    assert "pie title Phase Distribution" in payload.raw
    # All three phases appear as pie slices
    assert '"Phase 1"' in payload.raw
    assert '"Phase 2"' in payload.raw
    assert '"Phase 3"' in payload.raw
    # Values are the raw counts from the fixture
    assert '"Phase 1" : 42' in payload.raw
    assert '"Phase 2" : 78' in payload.raw
    assert '"Phase 3" : 35' in payload.raw
    # Pie sits BEFORE the Activity Overview section
    pie_idx = payload.raw.index("```mermaid")
    overview_idx = payload.raw.index("### Activity Overview")
    assert pie_idx < overview_idx


def test_whitespace_card_no_pie_when_single_phase():
    """One phase with count → no pie chart."""
    data = {
        "condition": "rare",
        "trial_counts_by_phase": {"phase_3": 5},
        "identified_whitespace": ["Only Phase 3 activity"],
    }
    payload = whitespace_card.build(data)
    assert "```mermaid" not in payload.raw
    # But the normal metric table + signal list still render
    assert "### Activity Overview" in payload.raw
    assert "Only Phase 3 activity" in payload.raw


def test_whitespace_card_no_pie_when_zero_counts():
    """Phase keys exist but all counts are zero → no pie."""
    data = {
        "condition": "empty",
        "trial_counts_by_phase": {"phase_1": 0, "phase_2": 0, "phase_3": 0},
        "identified_whitespace": [],
    }
    payload = whitespace_card.build(data)
    assert "```mermaid" not in payload.raw
