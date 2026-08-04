"""Extension test suite for Brand Strategy Hub — exercises the core flow
(create brand -> add competitor -> create segment -> SWOT -> gap analysis
-> pipeline handoff) against imperal_sdk's MockContext.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from imperal_sdk.testing import MockContext

import main as m
from schemas import (
    AddCompetitorParams, BuildContentStrategyHandoffParams,
    CreateBrandProfileParams, CreateTargetSegmentParams,
    ListBrandProfilesParams, ListCompetitorsParams, ListGapAnalysesParams,
    ListConnectedSitesParams,
    ListSWOTResultsParams, ListTargetSegmentsParams, RunGapAnalysisParams,
    RunSWOTAnalysisParams, UpdateBrandProfileParams,
)


@pytest.mark.asyncio
async def test_create_brand_profile_happy_path():
    ctx = MockContext()
    result = await m.create_brand_profile(
        ctx, CreateBrandProfileParams(
            brand_name="G4S Moldova", site_id="g4s.md",
            value_proposition="24/7 licensed security you can trust",
            unique_selling_points=["licensed guards", "24/7 response"],
        )
    )
    assert result.status == "success"
    assert result.data.brand_name == "G4S Moldova"


@pytest.mark.asyncio
async def test_update_brand_profile_patches_only_given_fields():
    ctx = MockContext()
    created = await m.create_brand_profile(
        ctx, CreateBrandProfileParams(brand_name="G4S Moldova")
    )
    brand_id = created.data.id

    result = await m.update_brand_profile(
        ctx, UpdateBrandProfileParams(brand_id=brand_id, mission="Protect what matters")
    )
    assert result.status == "success"
    assert result.data.mission == "Protect what matters"
    assert result.data.brand_name == "G4S Moldova"


@pytest.mark.asyncio
async def test_update_brand_profile_missing_brand_errors():
    ctx = MockContext()
    result = await m.update_brand_profile(
        ctx, UpdateBrandProfileParams(brand_id="nonexistent", mission="x")
    )
    assert result.status == "error"


@pytest.mark.asyncio
async def test_update_brand_profile_requires_at_least_one_field():
    ctx = MockContext()
    created = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="G4S"))
    result = await m.update_brand_profile(ctx, UpdateBrandProfileParams(brand_id=created.data.id))
    assert result.status == "error"


@pytest.mark.asyncio
async def test_list_brand_profiles():
    ctx = MockContext()
    await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="G4S"))
    await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Climtec"))
    result = await m.list_brand_profiles(ctx, ListBrandProfilesParams())
    assert result.status == "success"
    assert len(result.data.items) == 2


@pytest.mark.asyncio
async def test_add_competitor_profile_and_list():
    ctx = MockContext()
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="G4S"))
    result = await m.add_competitor_profile(
        ctx, AddCompetitorParams(
            brand_id=brand.data.id, name="SecureCo",
            strengths=["fast response"], weaknesses=["no local presence"],
        )
    )
    assert result.status == "success"
    assert result.data.name == "SecureCo"

    listed = await m.list_competitor_profiles(ctx, ListCompetitorsParams(brand_id=brand.data.id))
    assert len(listed.data.items) == 1


@pytest.mark.asyncio
async def test_add_competitor_missing_brand_errors():
    ctx = MockContext()
    result = await m.add_competitor_profile(
        ctx, AddCompetitorParams(brand_id="nonexistent", name="X")
    )
    assert result.status == "error"


@pytest.mark.asyncio
async def test_create_target_segment_and_list():
    ctx = MockContext()
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="G4S"))
    result = await m.create_target_segment(
        ctx, CreateTargetSegmentParams(
            brand_id=brand.data.id, segment_name="SMB office managers",
            pain_points=["theft risk"], needs=["affordable guard rotation"],
        )
    )
    assert result.status == "success"

    listed = await m.list_target_segments(ctx, ListTargetSegmentsParams(brand_id=brand.data.id))
    assert len(listed.data.items) == 1


@pytest.mark.asyncio
async def test_run_swot_analysis_uses_brand_and_competitors():
    ctx = MockContext()
    brand = await m.create_brand_profile(
        ctx, CreateBrandProfileParams(
            brand_name="G4S", value_proposition="Trusted 24/7 security",
            unique_selling_points=["licensed guards"],
        )
    )
    await m.add_competitor_profile(
        ctx, AddCompetitorParams(
            brand_id=brand.data.id, name="SecureCo",
            strengths=["cheaper pricing"], weaknesses=["slow response times"],
        )
    )
    result = await m.run_swot_analysis(ctx, RunSWOTAnalysisParams(brand_id=brand.data.id))
    assert result.status == "success"
    assert "licensed guards" in result.data.strengths
    assert any("slow response times" in o for o in result.data.opportunities)
    assert any("cheaper pricing" in t for t in result.data.threats)
    assert "Strengths" in result.data.body

    listed = await m.list_swot_results(ctx, ListSWOTResultsParams(brand_id=brand.data.id))
    assert len(listed.data.items) == 1


@pytest.mark.asyncio
async def test_run_swot_analysis_missing_brand_errors():
    ctx = MockContext()
    result = await m.run_swot_analysis(ctx, RunSWOTAnalysisParams(brand_id="nonexistent"))
    assert result.status == "error"


@pytest.mark.asyncio
async def test_run_gap_analysis_finds_unaddressed_needs():
    ctx = MockContext()
    brand = await m.create_brand_profile(
        ctx, CreateBrandProfileParams(
            brand_name="G4S", value_proposition="Trusted 24/7 security",
            unique_selling_points=["licensed guards"],
        )
    )
    segment = await m.create_target_segment(
        ctx, CreateTargetSegmentParams(
            brand_id=brand.data.id, segment_name="SMB office managers",
            needs=["affordable pricing plans"], pain_points=["unclear contracts"],
            preferred_channels=["local search"],
        )
    )
    result = await m.run_gap_analysis(
        ctx, RunGapAnalysisParams(brand_id=brand.data.id, segment_id=segment.data.id)
    )
    assert result.status == "success"
    assert any("affordable pricing plans" in g for g in result.data.gaps)
    assert any("local search" in r for r in result.data.recommendations)

    listed = await m.list_gap_analyses(ctx, ListGapAnalysesParams(brand_id=brand.data.id))
    assert len(listed.data.items) == 1


@pytest.mark.asyncio
async def test_run_gap_analysis_missing_segment_errors():
    ctx = MockContext()
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="G4S"))
    result = await m.run_gap_analysis(
        ctx, RunGapAnalysisParams(brand_id=brand.data.id, segment_id="nonexistent")
    )
    assert result.status == "error"


@pytest.mark.asyncio
async def test_build_content_strategy_handoff_shapes_payload():
    ctx = MockContext()
    brand = await m.create_brand_profile(
        ctx, CreateBrandProfileParams(
            brand_name="G4S Moldova", value_proposition="Trusted 24/7 security",
            unique_selling_points=["licensed guards", "24/7 response"],
        )
    )
    result = await m.build_content_strategy_handoff(
        ctx, BuildContentStrategyHandoffParams(
            brand_id=brand.data.id, site_id="g4s.md", target_languages=["ru", "ro"],
        )
    )
    assert result.status == "success"
    assert result.data.site_id == "g4s.md"
    assert result.data.domain == "g4s.md"
    assert result.data.brand_name == "G4S Moldova"
    assert result.data.target_languages == ["ru", "ro"]
    assert "licensed guards" in result.data.content_categories


@pytest.mark.asyncio
async def test_build_content_strategy_handoff_missing_brand_errors():
    ctx = MockContext()
    result = await m.build_content_strategy_handoff(
        ctx, BuildContentStrategyHandoffParams(brand_id="nonexistent", site_id="g4s.md")
    )
    assert result.status == "error"


# ──────────────────────────────────────────────────────────────────────────
# Panel rendering — regression coverage for the brand_detail_panel tab
# switcher. ui.Tabs was swapped out for a plain Button + ui.Call("tab=...")
# switcher because ui.Tabs is unproven anywhere else in this workspace's
# live panels, unlike Button/ui.Call which is the exact mechanism the
# Brands list already uses to open this very panel.
# ──────────────────────────────────────────────────────────────────────────

def _walk(node, seen_types):
    """Collect every UINode type in the tree, recursing into props."""
    node_type = getattr(node, "type", None)
    if node_type is not None:
        seen_types.add(node_type)
        props = getattr(node, "props", {}) or {}
        for value in props.values():
            if isinstance(value, list):
                for item in value:
                    _walk(item, seen_types)
            else:
                _walk(value, seen_types)
    return seen_types


@pytest.mark.asyncio
async def test_brand_detail_panel_no_brand_id_shows_empty_state():
    ctx = MockContext()
    node = await m.brand_detail_panel(ctx, brand_id="")
    assert getattr(node, "type", None) == "Empty"


@pytest.mark.asyncio
async def test_brand_detail_panel_unknown_brand_shows_empty_state():
    ctx = MockContext()
    node = await m.brand_detail_panel(ctx, brand_id="nonexistent")
    assert getattr(node, "type", None) == "Empty"


@pytest.mark.asyncio
async def test_brand_detail_panel_renders_without_ui_tabs():
    """ui.Tabs is not proven anywhere else in this workspace -- assert the
    panel tree never emits one, so nobody re-introduces it by accident."""
    ctx = MockContext()
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Climtec"))
    node = await m.brand_detail_panel(ctx, brand_id=brand.data.id)
    types = _walk(node, set())
    assert "Tabs" not in types
    assert "Button" in types
    # ui.Row is an alias that emits type "Stack" (direction="h"), not a
    # distinct "Row" node type -- assert on what the SDK actually emits.
    assert "Stack" in types


@pytest.mark.asyncio
async def test_brand_detail_panel_default_tab_is_profile():
    ctx = MockContext()
    brand = await m.create_brand_profile(
        ctx, CreateBrandProfileParams(brand_name="Climtec", mission="Keep homes warm")
    )
    node = await m.brand_detail_panel(ctx, brand_id=brand.data.id)
    rendered = repr(node)
    assert "Keep homes warm" in rendered


@pytest.mark.asyncio
async def test_brand_detail_panel_switches_to_swot_tab_via_param():
    ctx = MockContext()
    brand = await m.create_brand_profile(
        ctx, CreateBrandProfileParams(brand_name="Climtec", unique_selling_points=["fast install"])
    )
    await m.run_swot_analysis(ctx, RunSWOTAnalysisParams(brand_id=brand.data.id))
    node = await m.brand_detail_panel(ctx, brand_id=brand.data.id, tab="swot")
    rendered = repr(node)
    assert "fast install" in rendered


@pytest.mark.asyncio
async def test_brand_detail_panel_unknown_tab_falls_back_to_profile():
    ctx = MockContext()
    brand = await m.create_brand_profile(
        ctx, CreateBrandProfileParams(brand_name="Climtec", mission="Keep homes warm")
    )
    node = await m.brand_detail_panel(ctx, brand_id=brand.data.id, tab="not-a-real-tab")
    rendered = repr(node)
    assert "Keep homes warm" in rendered


@pytest.mark.asyncio
async def test_brand_detail_panel_empty_states_for_swot_gap_competitors_segments():
    """Every tab must render something sane (Empty prompt) before any data
    exists -- guards against a KeyError/crash on a brand-new brand."""
    ctx = MockContext()
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Climtec"))
    for tab in ("profile", "swot", "gap", "competitors", "segments"):
        node = await m.brand_detail_panel(ctx, brand_id=brand.data.id, tab=tab)
        assert getattr(node, "type", None) == "Stack"


@pytest.mark.asyncio
async def test_brands_panel_empty_state_still_has_create_form():
    """Even with zero brands, the sidebar must offer a real way to create
    the first one -- not just point the user at the chat box."""
    ctx = MockContext()
    node = await m.brands_panel(ctx)
    types = _walk(node, set())
    assert "Form" in types
    assert "Input" in types
    assert "Empty" in types


@pytest.mark.asyncio
async def test_brands_panel_with_brands_still_offers_create_form():
    ctx = MockContext()
    await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Climtec"))
    node = await m.brands_panel(ctx)
    types = _walk(node, set())
    assert "List" in types
    assert "Form" in types
    assert not _tree_repr_has_send_action(node)


@pytest.mark.asyncio
async def test_brand_detail_panel_shows_competitors_and_segments_when_present():
    ctx = MockContext()
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Climtec"))
    await m.add_competitor_profile(
        ctx, AddCompetitorParams(brand_id=brand.data.id, name="RivalCo", strengths=["cheap"])
    )
    await m.create_target_segment(
        ctx, CreateTargetSegmentParams(brand_id=brand.data.id, segment_name="Homeowners")
    )
    comp_node = await m.brand_detail_panel(ctx, brand_id=brand.data.id, tab="competitors")
    assert "RivalCo" in repr(comp_node)
    seg_node = await m.brand_detail_panel(ctx, brand_id=brand.data.id, tab="segments")
    assert "Homeowners" in repr(seg_node)


# ──────────────────────────────────────────────────────────────────────────
# Regression: every data-collecting action must be a real ui.Form the user
# fills in and submits directly (no chat needed) -- not a ui.Send button
# that just pre-types a chat message the user still has to send themselves.
# Goal: "a UI I control that reaches every detail without talking in chat."
# ──────────────────────────────────────────────────────────────────────────

def _find_forms(node, actions):
    """Collect the `action` prop of every Form node in the tree."""
    node_type = getattr(node, "type", None)
    if node_type == "Form":
        actions.append(getattr(node, "props", {}).get("action", ""))
    if node_type is not None:
        props = getattr(node, "props", {}) or {}
        for value in props.values():
            if isinstance(value, list):
                for item in value:
                    _find_forms(item, actions)
            else:
                _find_forms(value, actions)
    return actions


def _tree_repr_has_send_action(node) -> bool:
    """True if any UIAction(action='send', ...) appears anywhere in the tree."""
    return "action='send'" in repr(node) or 'action="send"' in repr(node)


@pytest.mark.asyncio
async def test_brand_detail_panel_has_no_send_to_chat_actions_anywhere():
    """No button/form in the whole panel should fall back to 'type this into
    chat yourself' -- every data-entry action must be a real embedded form."""
    ctx = MockContext()
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Climtec"))
    await m.add_competitor_profile(
        ctx, AddCompetitorParams(brand_id=brand.data.id, name="RivalCo", strengths=["cheap"])
    )
    await m.create_target_segment(
        ctx, CreateTargetSegmentParams(brand_id=brand.data.id, segment_name="Homeowners")
    )
    for tab in ("profile", "swot", "gap", "competitors", "segments"):
        node = await m.brand_detail_panel(ctx, brand_id=brand.data.id, tab=tab)
        assert not _tree_repr_has_send_action(node), f"tab={tab} still sends to chat instead of using a Form"


@pytest.mark.asyncio
async def test_profile_tab_has_edit_and_handoff_forms():
    ctx = MockContext()
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Climtec"))
    node = await m.brand_detail_panel(ctx, brand_id=brand.data.id, tab="profile")
    actions = _find_forms(node, [])
    assert "update_brand_profile" in actions
    assert "build_content_strategy_handoff" in actions


@pytest.mark.asyncio
async def test_competitors_tab_has_add_competitor_form():
    ctx = MockContext()
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Climtec"))
    node = await m.brand_detail_panel(ctx, brand_id=brand.data.id, tab="competitors")
    actions = _find_forms(node, [])
    assert "add_competitor_profile" in actions


@pytest.mark.asyncio
async def test_segments_tab_has_add_segment_form():
    ctx = MockContext()
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Climtec"))
    node = await m.brand_detail_panel(ctx, brand_id=brand.data.id, tab="segments")
    actions = _find_forms(node, [])
    assert "create_target_segment" in actions


@pytest.mark.asyncio
async def test_gap_tab_has_run_gap_analysis_form_once_a_segment_exists():
    ctx = MockContext()
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Climtec"))
    await m.create_target_segment(
        ctx, CreateTargetSegmentParams(brand_id=brand.data.id, segment_name="Homeowners")
    )
    node = await m.brand_detail_panel(ctx, brand_id=brand.data.id, tab="gap")
    actions = _find_forms(node, [])
    assert "run_gap_analysis" in actions


@pytest.mark.asyncio
async def test_gap_tab_without_any_segment_shows_hint_not_a_broken_form():
    ctx = MockContext()
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Climtec"))
    node = await m.brand_detail_panel(ctx, brand_id=brand.data.id, tab="gap")
    actions = _find_forms(node, [])
    assert "run_gap_analysis" not in actions
    assert "No target segments yet" in repr(node)


# ──────────────────────────────────────────────────────────────────────────
# Quick Add — sites already connected in WordPress Hub (or any future
# site-provider app registered in SITE_PROVIDER_APP_IDS) surface as one-click
# "create a brand for this site" buttons, via ctx.extensions.call IPC.
# ──────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_connected_sites_calls_every_registered_provider():
    ctx = MockContext()
    ctx.extensions.register(
        "wp-site-connector", "list_connected_sites",
        lambda **kw: [{"site_id": "g4s.md", "name": "G4S Moldova", "url": "https://g4s.md", "status": "connected"}],
    )
    sites, problems = await m.fetch_connected_sites(ctx)
    assert problems == []
    assert len(sites) == 1
    assert sites[0]["site_id"] == "g4s.md"
    assert sites[0]["name"] == "G4S Moldova"
    assert sites[0]["provider"] == "wp-site-connector"


@pytest.mark.asyncio
async def test_provider_slug_site_id_is_normalised_to_the_bare_domain():
    """WordPress Hub keys sites by slug ('g4s-md') while these hubs key them
    by domain ('g4s.md'). Quick Add must offer the DOMAIN form, otherwise a
    click would create a duplicate profile beside the existing one."""
    ctx = MockContext()
    ctx.extensions.register(
        "wp-site-connector", "list_connected_sites",
        lambda **kw: [{"site_id": "g4s-md", "name": "G4S Moldova",
                       "url": "https://www.g4s.md/", "status": "connected"}],
    )
    sites, problems = await m.fetch_connected_sites(ctx)
    assert problems == []
    assert sites[0]["site_id"] == "g4s.md"          # normalised, www stripped
    assert sites[0]["provider_site_id"] == "g4s-md"  # original kept for traceability


@pytest.mark.asyncio
async def test_fetch_connected_sites_reports_unreachable_provider_instead_of_hiding_it():
    """A provider that cannot be reached must be REPORTED, not swallowed --
    a silently missing Quick Add card is unfixable from the UI."""
    ctx = MockContext()  # no providers registered at all
    sites, problems = await m.fetch_connected_sites(ctx)
    assert sites == []
    assert len(problems) == 1
    assert problems[0]["provider"] == "wp-site-connector"
    assert problems[0]["reason"]  # carries a real cause, not an empty string


@pytest.mark.asyncio
async def test_brands_panel_shows_quick_add_for_unclaimed_connected_site():
    ctx = MockContext()
    ctx.extensions.register(
        "wp-site-connector", "list_connected_sites",
        lambda **kw: [{"site_id": "g4s.md", "name": "G4S Moldova", "url": "https://g4s.md", "status": "connected"}],
    )
    node = await m.brands_panel(ctx)
    rendered = repr(node)
    assert "Quick Add" in rendered
    assert "G4S Moldova" in rendered
    assert "create_brand_profile" in rendered


@pytest.mark.asyncio
async def test_brands_panel_quick_add_card_stays_visible_when_all_sites_tracked():
    """The card must never vanish -- when every site already has a brand it
    explains that, so the user can still see the feature exists."""
    ctx = MockContext()
    ctx.extensions.register(
        "wp-site-connector", "list_connected_sites",
        lambda **kw: [{"site_id": "g4s.md", "name": "G4S Moldova", "url": "https://g4s.md", "status": "connected"}],
    )
    await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="G4S Moldova", site_id="g4s.md"))
    node = await m.brands_panel(ctx)
    rendered = repr(node)
    assert "Quick Add" in rendered
    assert "already has a brand profile" in rendered
    # the already-tracked site must NOT be offered as a Quick Add button again
    quick_add_section = rendered.split("Quick Add")[1].split("New brand")[0]
    assert "create_brand_profile" not in quick_add_section


@pytest.mark.asyncio
async def test_brands_panel_quick_add_card_explains_unreachable_provider():
    """No provider reachable -> the card is still rendered and names the
    reason, instead of disappearing without a trace."""
    ctx = MockContext()  # no providers registered
    node = await m.brands_panel(ctx)
    rendered = repr(node)
    assert "Quick Add" in rendered
    assert "Could not read connected sites" in rendered
    assert "wp-site-connector" in rendered
    assert "Refresh" in rendered


@pytest.mark.asyncio
async def test_list_connected_sites_flags_already_tracked_sites():
    ctx = MockContext()
    ctx.extensions.register(
        "wp-site-connector", "list_connected_sites",
        lambda **kw: [
            {"site_id": "g4s.md", "name": "G4S Moldova", "url": "https://g4s.md", "status": "connected"},
            {"site_id": "climtec.md", "name": "Climtec", "url": "https://climtec.md", "status": "connected"},
        ],
    )
    await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="G4S Moldova", site_id="g4s.md"))
    result = await m.list_connected_sites(ctx, ListConnectedSitesParams())
    assert result.status == "success"
    by_id = {i.site_id: i for i in result.data.items}
    assert by_id["g4s.md"].already_tracked is True
    assert by_id["climtec.md"].already_tracked is False
    assert by_id["g4s.md"].provider == "wp-site-connector"


@pytest.mark.asyncio
async def test_list_connected_sites_surfaces_provider_failure_in_summary():
    """The diagnostic path: an unreachable provider must be named in the
    summary so an empty Quick Add list is explainable, not mysterious."""
    ctx = MockContext()  # no providers registered
    result = await m.list_connected_sites(ctx, ListConnectedSitesParams())
    assert result.status == "success"
    assert result.data.items == []
    assert "Could not read from" in result.summary
    assert "wp-site-connector" in result.summary
