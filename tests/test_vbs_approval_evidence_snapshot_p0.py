"""P0 immutable evidence-basis snapshot tests for VBS approval."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from imperal_sdk.testing import MockContext

import main as m
from schemas import (
    ActivateVisualBrandSystemParams,
    CreateBrandProfileParams,
    CreateVisualBrandSystemParams,
    InitializeVisualBrandWorkspaceParams,
    RegisterVisualEvidenceParams,
    ReviewVisualEvidenceParams,
)


@pytest.mark.asyncio
async def test_approved_vbs_retains_immutable_reviewed_evidence_snapshot():
    ctx = MockContext(user_id="owner", tenant_id="tenant-a")
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Snapshot brand"))
    brand_id = brand.data.id
    await m.initialize_visual_brand_workspace(
        ctx, InitializeVisualBrandWorkspaceParams(brand_id=brand_id, confirm_owner_claim=True)
    )
    evidence = await m.register_visual_evidence(
        ctx,
        RegisterVisualEvidenceParams(
            brand_id=brand_id,
            expected_workspace_version=1,
            source_url="https://example.org/snapshot-source",
            source_title="Original source title",
            observation="Original reviewed observation.",
        ),
    )
    reviewed = await m.review_visual_evidence(
        ctx,
        ReviewVisualEvidenceParams(
            evidence_id=evidence.data["id"],
            expected_status="discovered",
            expected_workspace_version=evidence.data["workspace_version"],
            decision="reviewed_valid",
            review_note="Reviewed for approval basis.",
        ),
    )
    draft = await m.create_visual_brand_system(
        ctx,
        CreateVisualBrandSystemParams(
            brand_id=brand_id,
            expected_workspace_version=reviewed.data.workspace_version,
            visual_intent="Grounded visual proof",
            realism_level="realistic",
            core_rules=["natural light"],
            prohibited_patterns=["text overlays"],
            change_note="Snapshot approval draft",
        ),
    )
    approved = await m.activate_visual_brand_system(
        ctx,
        ActivateVisualBrandSystemParams(
            vbs_id=draft.data["vbs_id"],
            expected_revision=1,
            expected_workspace_version=draft.data["workspace_version"],
            approval_note="Approved with reviewed evidence basis.",
        ),
    )
    assert approved.status == "success"

    saved = await ctx.store.get(m.VBS_SYSTEMS, draft.data["vbs_id"])
    snapshot = saved.data["approval_evidence_snapshot"]
    assert len(snapshot) == 1
    assert snapshot[0]["evidence_id"] == evidence.data["id"]
    assert snapshot[0]["status"] == "reviewed_valid"
    assert snapshot[0]["source_title"] == "Original source title"
    assert len(saved.data["approval_evidence_snapshot_hash"]) == 64

    live_evidence = await ctx.store.get(m.VBS_EVIDENCE, evidence.data["id"])
    await ctx.store.update(m.VBS_EVIDENCE, live_evidence.id, {**live_evidence.data, "source_title": "Changed later"})
    after = await ctx.store.get(m.VBS_SYSTEMS, draft.data["vbs_id"])
    assert after.data["approval_evidence_snapshot"] == snapshot
