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
    assert vbs.data["approval_audit_event_id"]
    assert vbs.data["approval_audit_chain_sequence"] > 0

    original_vbs_data = dict(vbs.data)
    await ctx.store.update(m.VBS_SYSTEMS, vbs.id, {**vbs.data, "approval_audit_event_id": "missing-event"})
    broken_link = await m.verify_visual_brand_approval_evidence_basis(
        ctx, VerifyVisualBrandApprovalEvidenceBasisParams(brand_id=brand_id, vbs_id=vbs.id)
    )
    assert broken_link.status == "success"
    assert broken_link.data.valid is False
    await ctx.store.update(m.VBS_SYSTEMS, vbs.id, original_vbs_data)

    approval_events = await ctx.store.query(m.VBS_AUDIT_EVENTS, where={"brand_id": brand_id}, limit=50)
    approval_event = next(item for item in approval_events.data if item.id == original_vbs_data["approval_audit_event_id"])
    await ctx.store.update(
        m.VBS_AUDIT_EVENTS,
        approval_event.id,
        {
            **approval_event.data,
            "immutable_metadata": {
                **approval_event.data["immutable_metadata"],
                "approval_evidence_snapshot_hash": "0" * 64,
            },
        },
    )
    event_tampered = await m.verify_visual_brand_approval_evidence_basis(
        ctx, VerifyVisualBrandApprovalEvidenceBasisParams(brand_id=brand_id, vbs_id=draft.data["vbs_id"])
    )
    assert event_tampered.status == "success"
    assert event_tampered.data.valid is False

    # Restore the event so this test independently proves a VBS-record snapshot mutation too.
    await ctx.store.update(m.VBS_AUDIT_EVENTS, approval_event.id, approval_event.data)
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
