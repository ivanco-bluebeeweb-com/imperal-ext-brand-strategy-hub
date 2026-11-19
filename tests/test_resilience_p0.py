"""Resilience tests for Brand Strategy Hub."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock
import pytest
from imperal_sdk.testing import MockContext

import main as m
import converters
from schemas import (
    CreateBrandProfileParams,
    ListConnectedSitesParams,
)


@pytest.mark.asyncio
async def test_converters_resilient_to_none_in_store():
    """Verify converters handle dicts with explicit None values without raising TypeError."""
    corrupt_brand_doc = {
        "id": "brand-none-1",
        "brand_name": "Test Brand",
        "unique_selling_points": None,
        "content_topics": None,
        "industry": None,
        "mission": None,
        "vision": None,
        "value_proposition": None,
        "tone_of_voice": None,
        "site_id": None,
    }

    # to_content_handoff
    handoff = converters.to_content_handoff(
        corrupt_brand_doc,
        brand_id="brand-none-1",
        site_id="site.md",
        domain="site.md",
        target_languages=["ru"],
    )
    assert handoff.brand_name == "Test Brand"
    assert handoff.content_categories == []
    assert handoff.domain == "site.md"

    # build_swot with None competitor/brand fields
    corrupt_competitors = [
        {
            "id": "comp-none-1",
            "name": "Rival",
            "strengths": None,
            "weaknesses": None,
            "notes": None,
            "url": None,
        }
    ]
    strengths, weaknesses, opportunities, threats = converters.build_swot(corrupt_brand_doc, corrupt_competitors)
    assert isinstance(strengths, list)
    assert isinstance(weaknesses, list)
    assert isinstance(opportunities, list)
    assert isinstance(threats, list)

    # build_gap_analysis with None segment fields
    corrupt_segment = {
        "id": "seg-none-1",
        "brand_id": "brand-none-1",
        "segment_name": "Target Audience",
        "pain_points": None,
        "needs": None,
        "demographics": None,
        "psychographics": None,
        "preferred_channels": None,
    }
    gaps, recommendations = converters.build_gap_analysis(corrupt_brand_doc, corrupt_segment)
    assert isinstance(gaps, list)
    assert isinstance(recommendations, list)


@pytest.mark.asyncio
async def test_ipc_timeout_and_error_handling():
    """Verify that external IPC calls survive timeouts and exceptions without crashing."""
    ctx = MockContext()

    # Case 1: Timeout simulation in list_connected_sites
    async def slow_call(*args, **kwargs):
        raise asyncio.TimeoutError("Simulated IPC timeout")

    ctx.extensions.call = AsyncMock(side_effect=slow_call)
    res = await m.list_connected_sites(ctx, ListConnectedSitesParams(limit=10))
    assert res is not None
    assert getattr(res, "data", None) is not None

    # Case 2: Exception simulation in list_connected_sites
    ctx.extensions.call = AsyncMock(side_effect=RuntimeError("IPC connection refused"))
    res_err = await m.list_connected_sites(ctx, ListConnectedSitesParams(limit=10))
    assert res_err is not None
    assert getattr(res_err, "data", None) is not None


@pytest.mark.asyncio
async def test_ui_panels_resilience_to_none_fields():
    """Verify UI tabs render safely even when brand fields in store are None."""
    ctx = MockContext()
    brand = await m.create_brand_profile(
        ctx, CreateBrandProfileParams(brand_name="PanelResilienceCo")
    )
    b_id = brand.data.id

    # Test all tabs in brand_detail_panel
    tabs = ["overview", "profile", "vbs", "competitors", "segments", "swot", "gap", "research", "export_import"]
    for tab in tabs:
        node = await m.brand_detail_panel(ctx, brand_id=b_id, tab=tab)
        assert node is not None
