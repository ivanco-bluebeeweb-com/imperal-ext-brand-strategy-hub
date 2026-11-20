import pytest
from imperal_sdk.testing import MockContext
from main import remove_candidate, _render_brand_detail_panel
from schemas import RemoveCandidateParams


@pytest.mark.asyncio
async def test_remove_candidate_flow():
    ctx = MockContext(user_id="imp_u_test", tenant_id="tenant-test")
    # Use create_brand_profile so MockContext store indexes it correctly
    from main import create_brand_profile
    from schemas import CreateBrandProfileParams

    res_brand = await create_brand_profile(
        ctx,
        CreateBrandProfileParams(
            brand_name="Test Brand",
            industry="security",
        ),
    )
    assert res_brand.status == "success"
    brand_id = res_brand.data.id

    # Seed snapshot with candidates
    snap_data = {
        "id": "snap1",
        "brand_id": brand_id,
        "is_current": True,
        "industry": "security",
        "landscape_summary": "Test landscape",
        "tracked_competitors": [],
        "candidate_competitors": ["Candidate One", "Candidate Two"],
        "candidate_details": [
            {"name": "Candidate One", "url": "https://c1.test", "notes": "C1 note"},
            {"name": "Candidate Two", "url": "https://c2.test", "notes": "C2 note"},
        ],
        "sourcing_trail": ["https://s1.test"],
    }
    await ctx.store.create("market_research_snapshots", snap_data)

    # Call remove_candidate for "Candidate One"
    params = RemoveCandidateParams(brand_id=brand_id, candidate_name="Candidate One")
    res = await remove_candidate(ctx, params)
    assert res.status == "success", f"remove_candidate failed: status={res.status}, msg={getattr(res, 'message', None)}, err={getattr(res, 'error', None)}"
    assert "Candidate One" in res.summary

    # Verify snapshot state
    snap_page = await ctx.store.query("market_research_snapshots", where={"brand_id": brand_id})
    assert len(snap_page.data) >= 1
    data = snap_page.data[0].data
    assert data["candidate_competitors"] == ["Candidate Two"]
    assert len(data["candidate_details"]) == 1
    assert data["candidate_details"][0]["name"] == "Candidate Two"


@pytest.mark.asyncio
async def test_remove_candidate_ui_trash_icon():
    ctx = MockContext()
    brand_id = "b456"

    # Seed brand
    await ctx.store.create("brand_profiles", {
        "id": brand_id,
        "brand_name": "Test Brand",
        "industry": "construction",
    })

    # Seed snapshot with candidate details
    snap_data = {
        "id": "snap2",
        "brand_id": brand_id,
        "is_current": True,
        "industry": "construction",
        "candidate_competitors": ["Builder Alpha"],
        "candidate_details": [
            {"name": "Builder Alpha", "url": "https://alpha.test", "notes": "Alpha note"},
        ],
        "sourcing_trail": [],
    }
    await ctx.store.create("market_research_snapshots", snap_data)

    # Render panel
    panel = await _render_brand_detail_panel(ctx, brand_id, tab="competitors")

    # Serialize or inspect panel structure
    panel_dump = str(panel.model_dump() if hasattr(panel, "model_dump") else panel)

    # Check for Trash2 icon and remove_candidate call
    assert "Trash2" in panel_dump
    assert "remove_candidate" in panel_dump
    assert "Builder Alpha" in panel_dump
