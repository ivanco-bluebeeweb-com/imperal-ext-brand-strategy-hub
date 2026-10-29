import json
import pytest
from imperal_sdk.testing import MockContext
from main import (
    create_brand_profile,
    add_brand_competitor,
    create_target_segment,
    run_swot_analysis,
    export_brand_project,
    import_brand_project,
    _render_brand_detail_panel,
)
from schemas import (
    CreateBrandProfileParams,
    AddCompetitorParams,
    CreateTargetSegmentParams,
    RunSWOTAnalysisParams,
    ExportBrandProjectParams,
    ImportBrandProjectParams,
)

@pytest.mark.asyncio
async def test_export_import_full():
    ctx1 = MockContext(user_id="u1", tenant_id="t1")
    ctx2 = MockContext(user_id="u2", tenant_id="t2")

    p = await create_brand_profile(
        ctx1,
        CreateBrandProfileParams(
            brand_name="RocketCorp",
            mission="Launch reliably",
            vision="Orbit",
            value_proposition="Low cost",
            tone_of_voice="Direct",
            unique_selling_points=["Reusability"],
            content_topics=["Aerospace"],
        ),
    )
    b_id = p.data.id

    await add_brand_competitor(
        ctx1,
        AddCompetitorParams(
            brand_id=b_id,
            name="OldSpace Inc",
            notes="Slow and costly",
        ),
    )

    await create_target_segment(
        ctx1,
        CreateTargetSegmentParams(
            brand_id=b_id,
            segment_name="Sat Builders",
        ),
    )

    await run_swot_analysis(
        ctx1,
        RunSWOTAnalysisParams(
            brand_id=b_id,
        ),
    )

    # Export
    exp = await export_brand_project(ctx1, ExportBrandProjectParams(brand_id=b_id))
    assert exp.status == "success"
    raw_json = exp.data.json_data
    assert raw_json

    data = json.loads(raw_json)
    assert data["brand_id"] == b_id
    assert data["brand_profile"]["data"]["brand_name"] == "RocketCorp"
    assert len(data["collections"]["competitor_profiles"]) == 1
    assert len(data["collections"]["target_segments"]) == 1
    assert len(data["collections"]["swot_results"]) == 1

    # Import into ctx2 (cross-account)
    imp = await import_brand_project(ctx2, ImportBrandProjectParams(json_data=raw_json))
    assert imp.status == "success"
    assert imp.data.brand_id == b_id

    # Verify ctx2 has data
    b2 = await ctx2.store.get("brand_profiles", b_id)
    assert b2 is not None
    assert b2.data["brand_name"] == "RocketCorp"
    assert b2.data["mission"] == "Launch reliably"

    comps = await ctx2.store.query("competitor_profiles", where={"brand_id": b_id})
    assert len(comps.data) == 1
    assert comps.data[0].data["name"] == "OldSpace Inc"

    segs = await ctx2.store.query("target_segments", where={"brand_id": b_id})
    assert len(segs.data) == 1
    assert segs.data[0].data["segment_name"] == "Sat Builders"

    swots = await ctx2.store.query("swot_results", where={"brand_id": b_id})
    assert len(swots.data) == 1
    assert "Reusability" in swots.data[0].data["strengths"]

@pytest.mark.asyncio
async def test_panel_has_export_and_import():
    ctx = MockContext(user_id="u1", tenant_id="t1")
    p = await create_brand_profile(
        ctx,
        CreateBrandProfileParams(
            brand_name="PanelTest",
            mission="Testing panel UI",
        ),
    )
    b_id = p.data.id

    panel = await _render_brand_detail_panel(ctx, brand_id=b_id, tab="profile")
    serialized = str(panel)
    assert "export_brand_project" in serialized
    assert "import_brand_project" in serialized
    assert "Export Project (JSON)" in serialized
    assert "Import Project (JSON)" in serialized

def test_speed_re_and_backups_exist():
    import os
    assert os.path.exists("scripts/speed_re.asi")
    assert os.path.exists("backups/main.py.bak")
    assert os.path.exists("backups/schemas.py.bak")
    with open("scripts/speed_re.asi") as f:
        content = f.read()
    assert "Phase:" in content
    assert "export_brand_project" in content
    assert "import_brand_project" in content

