import pytest
from imperal_sdk.testing import MockContext

import main as m
from schemas import (
    CreateBrandProfileParams,
    DeleteBrandProfileParams,
    EraseBrandProjectDataParams,
    AddCompetitorParams,
)


@pytest.mark.asyncio
async def test_erase_brand_project_data_clears_content_keeps_profile():
    ctx = MockContext(user_id="test-owner", tenant_id="tenant-test")

    # 1. Create brand profile
    brand_res = await m.create_brand_profile(
        ctx,
        CreateBrandProfileParams(
            brand_name="Test Brand Erase",
            industry="Security",
        ),
    )
    assert brand_res.status == "success"
    brand_id = brand_res.data.id

    # 2. Add competitor
    comp_res = await m.add_brand_competitor(
        ctx,
        AddCompetitorParams(
            brand_id=brand_id,
            name="Competitor 1",
            url="https://comp1.test",
        ),
    )
    assert comp_res.status == "success"

    # Verify competitor exists before erase
    comps_before = await ctx.store.query("competitor_profiles", where={"brand_id": brand_id})
    assert len(comps_before.data) == 1

    # 3. Call erase_brand_project_data
    erase_res = await m.erase_brand_project_data(
        ctx,
        EraseBrandProjectDataParams(brand_id=brand_id),
    )
    assert erase_res.status == "success"

    # 4. Brand profile STILL EXISTS
    brand_after = await ctx.store.get("brand_profiles", brand_id)
    assert brand_after is not None
    assert brand_after.data["brand_name"] == "Test Brand Erase"

    # 5. Competitor is deleted
    comps_after = await ctx.store.query("competitor_profiles", where={"brand_id": brand_id})
    assert len(comps_after.data) == 0


@pytest.mark.asyncio
async def test_delete_brand_profile_removes_profile_and_content():
    ctx = MockContext(user_id="test-owner", tenant_id="tenant-test")

    brand_res = await m.create_brand_profile(
        ctx,
        CreateBrandProfileParams(
            brand_name="Test Brand Full Delete",
            industry="Security",
        ),
    )
    assert brand_res.status == "success"
    brand_id = brand_res.data.id

    await m.add_brand_competitor(
        ctx,
        AddCompetitorParams(
            brand_id=brand_id,
            name="Competitor Delete",
            url="https://comp-del.test",
        ),
    )

    del_res = await m.delete_brand_profile(
        ctx,
        DeleteBrandProfileParams(brand_id=brand_id),
    )
    assert del_res.status == "success"

    brand_after = await ctx.store.get("brand_profiles", brand_id)
    assert brand_after is None

    comps_after = await ctx.store.query("competitor_profiles", where={"brand_id": brand_id})
    assert len(comps_after.data) == 0


@pytest.mark.asyncio
async def test_panel_has_both_erase_and_delete_project_buttons():
    ctx = MockContext(user_id="test-owner", tenant_id="tenant-test")
    brand_id = "test-brand-ui-panel"

    await ctx.store.create(
        "brand_profiles",
        {
            "id": brand_id,
            "brand_name": "UI Panel Brand",
            "industry": "Marketing",
        },
    )

    panel = await m._render_brand_detail_panel(ctx, brand_id)
    panel_dump = str(panel.model_dump() if hasattr(panel, "model_dump") else panel)

    assert "Erase all project data" in panel_dump
    assert "Delete Project" in panel_dump

    # Test erase confirmation modal
    panel_erase = await m._render_brand_detail_panel(ctx, brand_id, show_erase="1")
    erase_dump = str(panel_erase.model_dump() if hasattr(panel_erase, "model_dump") else panel_erase)
    assert "Erase All Project Data" in erase_dump
    assert "erase_brand_project_data" in erase_dump

    # Test delete confirmation modal
    panel_delete = await m._render_brand_detail_panel(ctx, brand_id, show_delete="1")
    delete_dump = str(panel_delete.model_dump() if hasattr(panel_delete, "model_dump") else panel_delete)
    assert "Delete Project" in delete_dump
    assert "delete_brand_profile" in delete_dump
