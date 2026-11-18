"""Tests for auto-discovery and auto-addition of Competitors and Target Segments."""

import pytest
from imperal_sdk.testing import MockContext

from main import (
    create_brand_profile,
    add_brand_competitor,
    auto_add_competitors,
    list_brand_competitors,
)
from schemas import (
    CreateBrandProfileParams,
    AddCompetitorParams,
    ListCompetitorsParams,
    AutoAddCompetitorsParams,
    MarketSignal,
)


@pytest.mark.asyncio
async def test_auto_add_competitors_without_auxiliary_data():
    """Auto-add competitors autonomously using industry benchmark heuristics when no signals/candidates are passed."""
    ctx = MockContext()
    brand = await create_brand_profile(
        ctx,
        CreateBrandProfileParams(
            brand_name="Shield Corp",
            industry="security",
            value_proposition="Enterprise security systems",
        ),
    )
    assert brand.status == "success"
    brand_id = brand.data.id

    # Run auto_add_competitors without auxiliary data
    result = await auto_add_competitors(ctx, AutoAddCompetitorsParams(brand_id=brand_id))
    assert result.status == "success"
    assert len(result.data.items) > 0
    assert "autonomous industry discovery" in result.summary

    # Verify they were actually persisted in store
    comp_list = await list_brand_competitors(ctx, ListCompetitorsParams(brand_id=brand_id))
    assert len(comp_list.data.items) == len(result.data.items)
    names = [c.name for c in comp_list.data.items]
    assert "Securitas" in names or "Allied Universal" in names or "G4S" in names


@pytest.mark.asyncio
async def test_auto_add_competitors_with_auxiliary_signals():
    """Auto-add competitors extracting candidates from provided auxiliary signals."""
    ctx = MockContext()
    brand = await create_brand_profile(
        ctx,
        CreateBrandProfileParams(
            brand_name="Nordic Coffee",
            industry="beverage",
        ),
    )
    brand_id = brand.data.id

    signals = [
        MarketSignal(
            url="https://market-news.com/local-roasters",
            title="Top Roasters",
            summary="Artisan coffee comparison",
            candidate_competitor_name="Fika Beans",
        ),
        MarketSignal(
            url="https://market-news.com/espresso-co",
            summary="RoastMasters espresso analysis",
            candidate_competitor_name="RoastMasters",
        ),
    ]

    result = await auto_add_competitors(
        ctx,
        AutoAddCompetitorsParams(
            brand_id=brand_id,
            signals=signals,
            candidates=["Caffè Nero"],
        ),
    )
    assert result.status == "success"
    assert len(result.data.items) == 3
    assert "from auxiliary signals" in result.summary

    comp_list = await list_brand_competitors(ctx, ListCompetitorsParams(brand_id=brand_id))
    assert len(comp_list.data.items) == 3
    names = {c.name for c in comp_list.data.items}
    assert names == {"Fika Beans", "RoastMasters", "Caffè Nero"}


@pytest.mark.asyncio
async def test_auto_add_competitors_deduplicates_existing():
    """Auto-add competitors skips competitors that already exist in the brand."""
    ctx = MockContext()
    brand = await create_brand_profile(
        ctx,
        CreateBrandProfileParams(
            brand_name="Shield Corp",
            industry="security",
        ),
    )
    brand_id = brand.data.id

    # Pre-add Securitas manually
    await add_brand_competitor(
        ctx,
        AddCompetitorParams(brand_id=brand_id, name="Securitas"),
    )

    result = await auto_add_competitors(
        ctx,
        AutoAddCompetitorsParams(
            brand_id=brand_id,
            candidates=["Securitas", "NewGuard"],
        ),
    )
    assert result.status == "success"
    assert len(result.data.items) == 1
    assert result.data.items[0].name == "NewGuard"


@pytest.mark.asyncio
async def test_auto_add_segments_without_auxiliary_data():
    """Auto-add target segments autonomously using industry audience benchmarks when no signals/candidates are passed."""
    ctx = MockContext()
    brand = await create_brand_profile(
        ctx,
        CreateBrandProfileParams(
            brand_name="Aero Logistics",
            industry="logistics",
            value_proposition="Next-day enterprise freight forwarding",
        ),
    )
    brand_id = brand.data.id

    from main import auto_add_segments, list_target_segments
    from schemas import AutoAddSegmentsParams, ListTargetSegmentsParams

    result = await auto_add_segments(ctx, AutoAddSegmentsParams(brand_id=brand_id))
    assert result.status == "success"
    assert len(result.data.items) > 0
    assert "autonomous audience discovery" in result.summary

    # Verify they were actually persisted in store
    seg_list = await list_target_segments(ctx, ListTargetSegmentsParams(brand_id=brand_id))
    assert len(seg_list.data.items) >= len(result.data.items)
    names = [s.segment_name for s in seg_list.data.items]
    assert any("Logistics" in n or "Supply Chain" in n or "Enterprise" in n or "B2B" in n for n in names)


@pytest.mark.asyncio
async def test_auto_add_segments_with_auxiliary_candidates():
    """Auto-add target segments using auxiliary signals or candidate definitions."""
    ctx = MockContext()
    brand = await create_brand_profile(
        ctx,
        CreateBrandProfileParams(
            brand_name="SaaS Metrics Pro",
            industry="software",
        ),
    )
    brand_id = brand.data.id

    from main import auto_add_segments, list_target_segments
    from schemas import AutoAddSegmentsParams, ListTargetSegmentsParams, CreateTargetSegmentParams

    candidates = [
        CreateTargetSegmentParams(
            brand_id=brand_id,
            segment_name="Growth Marketing Leads",
            demographics="VP Marketing at series A-C startups",
            psychographics="Obsessed with CAC/LTV and attribution accuracy",
            pain_points=["Disjointed attribution data"],
            needs=["Real-time cohort retention dashboard"],
            preferred_channels=["LinkedIn", "Growth Hackers"],
        ),
        CreateTargetSegmentParams(
            brand_id=brand_id,
            segment_name="RevOps Directors",
            demographics="Heads of RevOps at scale-ups",
            psychographics="Efficiency-focused, process-driven",
            pain_points=["Messy CRM integration"],
            needs=["One-click Salesforce and Stripe syncing"],
            preferred_channels=["RevOps Co-op", "Direct Search"],
        ),
    ]

    result = await auto_add_segments(
        ctx,
        AutoAddSegmentsParams(
            brand_id=brand_id,
            candidates=candidates,
        ),
    )
    assert result.status == "success"
    assert len(result.data.items) == 2
    assert "from auxiliary signals/candidates" in result.summary

    seg_list = await list_target_segments(ctx, ListTargetSegmentsParams(brand_id=brand_id))
    names = {s.segment_name for s in seg_list.data.items}
    assert "Growth Marketing Leads" in names
    assert "RevOps Directors" in names


@pytest.mark.asyncio
async def test_auto_add_segments_deduplicates_existing():
    """Auto-add target segments skips segments that already exist in the brand."""
    ctx = MockContext()
    brand = await create_brand_profile(
        ctx,
        CreateBrandProfileParams(
            brand_name="SaaS Metrics Pro",
            industry="software",
        ),
    )
    brand_id = brand.data.id

    from main import create_target_segment, auto_add_segments
    from schemas import CreateTargetSegmentParams, AutoAddSegmentsParams

    # Pre-add a segment
    await create_target_segment(
        ctx,
        CreateTargetSegmentParams(
            brand_id=brand_id,
            segment_name="Growth Marketing Leads",
        ),
    )

    result = await auto_add_segments(
        ctx,
        AutoAddSegmentsParams(
            brand_id=brand_id,
            candidates=[
                CreateTargetSegmentParams(brand_id=brand_id, segment_name="Growth Marketing Leads"),
                CreateTargetSegmentParams(brand_id=brand_id, segment_name="New Unique Segment"),
            ],
        ),
    )
    assert result.status == "success"
    assert len(result.data.items) == 1
    assert result.data.items[0].segment_name == "New Unique Segment"


@pytest.mark.asyncio
async def test_panel_has_auto_add_buttons_in_competitors_and_segments_tabs():
    """Verify that the competitors and segments tabs in brand_detail_panel offer 1-click auto-add actions."""
    from main import brand_detail_panel

    ctx = MockContext()
    brand = await create_brand_profile(
        ctx,
        CreateBrandProfileParams(
            brand_name="Auto Brand Test",
            industry="security",
        ),
    )
    brand_id = brand.data.id

    # Competitors tab
    comp_node = await brand_detail_panel(ctx, brand_id=brand_id, tab="competitors")
    comp_repr = repr(comp_node)
    assert "auto_add_competitors" in comp_repr
    assert "Auto-discover" in comp_repr

    # Segments tab
    seg_node = await brand_detail_panel(ctx, brand_id=brand_id, tab="segments")
    seg_repr = repr(seg_node)
    assert "auto_add_segments" in seg_repr
    assert "Auto-discover" in seg_repr
