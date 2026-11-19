"""Tests for market research expansion, brand auto-enrichment, and candidate promotion."""

import pytest
from imperal_sdk.testing import MockContext

from main import (
    create_brand_profile,
    run_market_research,
    promote_candidate,
    list_brand_competitors,
    _ensure_brand_context,
)
from schemas import (
    CreateBrandProfileParams,
    RunMarketResearchParams,
    PromoteCandidateParams,
    ListCompetitorsParams,
    MarketSignal,
    CandidateCompetitor,
)


@pytest.mark.asyncio
async def test_ensure_brand_context_fills_missing_fields():
    ctx = MockContext(user_id="imp_u_test", tenant_id="tenant-test")
    res = await create_brand_profile(
        ctx,
        CreateBrandProfileParams(
            brand_name="Nordic Minimal Wood",
            industry="Furniture Design",
            site_id="nordicwood.se",
        ),
    )
    assert res.status == "success"
    brand_id = res.data.id

    enriched = await _ensure_brand_context(ctx, brand_id)
    assert enriched["ok"] is True
    brand_data = enriched["brand"]
    assert brand_data["brand_name"] == "Nordic Minimal Wood"
    assert brand_data["industry"] == "Furniture Design"
    assert len(brand_data.get("value_proposition", "")) > 0 or len(brand_data.get("mission", "")) > 0
    assert len(brand_data.get("unique_selling_points", [])) > 0

    segments = await ctx.store.query("target_segments", where={"brand_id": brand_id})
    assert len(segments.data) >= 1


@pytest.mark.asyncio
async def test_market_research_candidate_details_and_promotion():
    ctx = MockContext(user_id="imp_u_test", tenant_id="tenant-test")
    res = await create_brand_profile(
        ctx,
        CreateBrandProfileParams(
            brand_name="Velox Logistics",
            industry="Freight & Supply Chain",
            site_id="velox.io",
        ),
    )
    brand_id = res.data.id

    signals = [
        MarketSignal(
            url="https://example.com/top-logistics",
            title="Logistics 2026",
            summary="FreightWave leads automated freight.",
            candidate_competitor_name="FreightWave",
        ),
    ]
    candidate_details = [
        CandidateCompetitor(
            name="FreightWave",
            url="https://freightwave.io",
            strengths=["Automation"],
            weaknesses=["High rates"],
            notes="Direct competitor",
            source="example.com",
        ),
    ]

    research_res = await run_market_research(
        ctx,
        RunMarketResearchParams(
            brand_id=brand_id,
            signals=signals,
            candidate_details=candidate_details,
        ),
    )
    assert research_res.status == "success"

    snapshots = await ctx.store.query("market_research_snapshots", where={"brand_id": brand_id})
    assert len(snapshots.data) == 1
    assert "FreightWave" in snapshots.data[0].data["candidate_competitors"]

    promote_res = await promote_candidate(
        ctx,
        PromoteCandidateParams(
            brand_id=brand_id,
            candidate_name="FreightWave",
            url="https://freightwave.io",
            strengths=["Automation"],
            weaknesses=["High rates"],
            notes="Direct competitor",
        ),
    )
    assert promote_res.status == "success"

    comps_res = await list_brand_competitors(ctx, ListCompetitorsParams(brand_id=brand_id))
    assert comps_res.status == "success"
    assert len(comps_res.data.items) == 1
    assert comps_res.data.items[0].name == "FreightWave"


@pytest.mark.asyncio
async def test_run_market_research_autonomous_discovery_when_no_signals():
    ctx = MockContext(user_id="imp_u_test", tenant_id="tenant-test")
    res = await create_brand_profile(
        ctx,
        CreateBrandProfileParams(
            brand_name="CyberGuard",
            industry="Cybersecurity & Managed SOC",
            site_id="cyberguard.io",
        ),
    )
    brand_id = res.data.id

    # Run market research with empty signals (as clicking RUN in panel UI)
    research_res = await run_market_research(
        ctx,
        RunMarketResearchParams(
            brand_id=brand_id,
            signals=[],
        ),
    )
    assert research_res.status == "success"
    snapshot = research_res.data
    assert snapshot.is_current is True
    # Verify autonomous discovery generated candidates and sourcing trail
    assert len(snapshot.candidate_competitors) > 0
    assert len(snapshot.candidate_details) > 0
    assert len(snapshot.sourcing_trail) > 0
    assert any("Cybersecurity" in trail or "search" in trail.lower() or "directory" in trail.lower() for trail in snapshot.sourcing_trail)


@pytest.mark.asyncio
async def test_market_research_filters_out_aggregators_and_directories():
    """Verify that aggregators like Angi, Houzz, Yelp, Thumbtack, Clutch etc.
    are never suggested as candidate competitors."""
    ctx = MockContext(user_id="imp_u_test", tenant_id="tenant-test")
    res = await create_brand_profile(
        ctx,
        CreateBrandProfileParams(
            brand_name="TRD Builders",
            industry="home remodeling & general contracting",
            site_id="trdbuilders.com",
        ),
    )
    brand_id = res.data.id

    # Run market research autonomously
    research_res = await run_market_research(
        ctx,
        RunMarketResearchParams(
            brand_id=brand_id,
            signals=[],
        ),
    )
    assert research_res.status == "success"
    snapshot = research_res.data

    # Ensure none of the candidate competitors or their URLs are aggregators
    from main import AGGREGATOR_DOMAINS
    for cand in snapshot.candidate_competitors:
        assert not any(agg in cand.lower() for agg in ["angi", "houzz", "yelp", "thumbtack", "clutch", "directory"]), f"Aggregator found in candidates: {cand}"

    for detail in snapshot.candidate_details:
        cand_url = getattr(detail, "url", "") if not isinstance(detail, dict) else detail.get("url", "")
        cand_name = getattr(detail, "name", "") if not isinstance(detail, dict) else detail.get("name", "")
        cand_url = cand_url.lower()
        cand_name = cand_name.lower()
        for agg in AGGREGATOR_DOMAINS:
            assert agg not in cand_url, f"Aggregator domain {agg} found in candidate url {cand_url}"
        assert not any(kw in cand_name for kw in ["directory", "aggregator", "marketplace", "finder"]), f"Aggregator name keyword found: {cand_name}"
