"""P0 integrity checks for the immutable evidence basis stored on VBS approval."""
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
    CreateVisualProfileParams,
    InitializeVisualBrandWorkspaceParams,
    RegisterVisualEvidenceParams,
    ReviewVisualEvidenceParams,
    VerifyVisualBrandApprovalEvidenceBasisParams,
)


@pytest.mark.asyncio
async def test_tampered_approved_evidence_basis_is_reported_and_blocks_profile_draft():
    ctx = MockContext(user_id="owner", tenant_id="tenant-a")
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Basis integrity brand"))
    brand_id = brand.data.id
    await m.initialize_visual_brand_workspace(
        ctx, InitializeVisualBrandWorkspaceParams(brand_id=brand_id, confirm_owner_claim=True)
    )
    evidence = await m.register_visual_evidence(
        ctx,
        RegisterVisualEvidenceParams(
            brand_id=brand_id,
            expected_workspace_version=1,
            source_url="https://example.org/basis-integrity",
            observation="Reviewed basis observation.",
        ),
    )
    reviewed = await m.review_visual_evidence(
        ctx,
        ReviewVisualEvidenceParams(
            evidence_id=evidence.data["id"],
            expected_status="discovered",
            expected_workspace_version=evidence.data["workspace_version"],
            decision="reviewed_valid",
            review_note="Reviewed.",
        ),
    )
    draft = await m.create_visual_brand_system(
        ctx,
        CreateVisualBrandSystemParams(
            brand_id=brand_id,
            expected_workspace_version=reviewed.data.workspace_version,
            visual_intent="Grounded proof",
        ),
    )
    approved = await m.activate_visual_brand_system(
        ctx,
        ActivateVisualBrandSystemParams(
            vbs_id=draft.data["vbs_id"],
            expected_revision=1,
            expected_workspace_version=draft.data["workspace_version"],
        ),
    )
    assert approved.status == "success"

    vbs = await ctx.store.get(m.VBS_SYSTEMS, draft.data["vbs_id"])
    tampered_snapshot = [dict(item, observation="Tampered after approval.") for item in vbs.data["approval_evidence_snapshot"]]
    await ctx.store.update(m.VBS_SYSTEMS, vbs.id, {**vbs.data, "approval_evidence_snapshot": tampered_snapshot})

    checked = await m.verify_visual_brand_approval_evidence_basis(
        ctx, VerifyVisualBrandApprovalEvidenceBasisParams(brand_id=brand_id, vbs_id=vbs.id)
    )
    assert checked.status == "success"
    assert checked.data.valid is False

    blocked = await m.create_visual_profile(
        ctx,
        CreateVisualProfileParams(
            brand_id=brand_id,
            expected_workspace_version=approved.data["workspace_version"],
            evidence_ids=[evidence.data["id"]],
            profile_summary="Blocked profile.",
            art_direction="Grounded.",
        ),
    )
    assert blocked.status == "error"
    assert blocked.error_code == "VBS_APPROVAL_EVIDENCE_BASIS_INVALID"
