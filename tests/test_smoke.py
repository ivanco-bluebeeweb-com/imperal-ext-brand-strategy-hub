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
