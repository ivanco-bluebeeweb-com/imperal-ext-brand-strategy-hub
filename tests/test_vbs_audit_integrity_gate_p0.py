"""P0 integrity gate tests for critical VBS mutations."""
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
    SetBrandMembershipParams,
)


async def _workspace(ctx):
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Integrity gate brand"))
    initialized = await m.initialize_visual_brand_workspace(
        ctx, InitializeVisualBrandWorkspaceParams(brand_id=brand.data.id, confirm_owner_claim=True)
    )
    return brand.data.id, initialized.data["version"]


async def _tamper_first_sealed_audit(ctx, brand_id):
    page = await ctx.store.query(m.VBS_AUDIT_EVENTS, where={"brand_id": brand_id}, limit=20)
    event = next(item for item in page.data if item.data.get("integrity_hash"))
    await ctx.store.update(m.VBS_AUDIT_EVENTS, event.id, {**event.data, "details": "tampered"})


@pytest.mark.asyncio
async def test_failed_integrity_blocks_membership_change_without_advancing_workspace():
    owner = MockContext(user_id="owner", tenant_id="tenant-a")
    brand_id, version = await _workspace(owner)
    await _tamper_first_sealed_audit(owner, brand_id)

    blocked = await m.set_brand_membership(
        owner,
        SetBrandMembershipParams(
            brand_id=brand_id, user_id="editor", role="editor", expected_workspace_version=version
        ),
    )
    assert blocked.status == "error"
    assert blocked.error_code == "VBS_AUDIT_INTEGRITY_FAILED"
    memberships = await owner.store.query(m.VBS_MEMBERSHIPS, where={"brand_id": brand_id}, limit=20)
    assert [item for item in memberships.data if item.data.get("user_id") == "editor"] == []
    workspace = await m._workspace_for_brand(owner, brand_id)
    assert workspace.data["version"] == version


@pytest.mark.asyncio
async def test_failed_integrity_blocks_evidence_review_and_vbs_approval():
    owner = MockContext(user_id="owner", tenant_id="tenant-a")
    brand_id, version = await _workspace(owner)
    draft = await m.create_visual_brand_system(
        owner,
        CreateVisualBrandSystemParams(
            brand_id=brand_id,
            expected_workspace_version=version,
            visual_intent="Calm commercial realism",
            realism_level="realistic",
            core_rules=["natural light"],
            prohibited_patterns=["text overlays"],
            change_note="First draft",
        ),
    )
    evidence = await m.register_visual_evidence(
        owner,
        RegisterVisualEvidenceParams(
            brand_id=brand_id,
            expected_workspace_version=draft.data["workspace_version"],
            source_url="https://example.org/reference",
            source_title="Reference",
            observation="Reference evidence",
        ),
    )
    await _tamper_first_sealed_audit(owner, brand_id)

    paused_panel = await m.brand_detail_panel(owner, brand_id=brand_id, tab="visual_system")
    rendered_paused = repr(paused_panel)
    assert "Critical changes paused — audit integrity check failed" in rendered_paused
    assert "Save review decision" not in rendered_paused
    assert "Approve as current" not in rendered_paused
    assert "Save member role" not in rendered_paused

    review = await m.review_visual_evidence(
        owner,
        ReviewVisualEvidenceParams(
            evidence_id=evidence.data["id"],
            expected_status="discovered",
            expected_workspace_version=evidence.data["workspace_version"],
            decision="reviewed_valid",
            review_note="Reviewed",
        ),
    )
    assert review.status == "error"
    assert review.error_code == "VBS_AUDIT_INTEGRITY_FAILED"

    approval = await m.activate_visual_brand_system(
        owner,
        ActivateVisualBrandSystemParams(
            vbs_id=draft.data["vbs_id"],
            expected_revision=draft.data["revision"],
            expected_workspace_version=evidence.data["workspace_version"],
            approval_note="Approve",
        ),
    )
    assert approval.status == "error"
    assert approval.error_code == "VBS_AUDIT_INTEGRITY_FAILED"
    evidence_record = await owner.store.get(m.VBS_EVIDENCE, evidence.data["id"])
    draft_record = await owner.store.get(m.VBS_SYSTEMS, draft.data["vbs_id"])
    assert evidence_record.data["status"] == "discovered"
    assert draft_record.data["status"] == "draft"


@pytest.mark.asyncio
async def test_unsealed_legacy_event_does_not_block_critical_mutation():
    owner = MockContext(user_id="owner", tenant_id="tenant-a")
    brand_id, version = await _workspace(owner)
    await owner.store.create(
        m.VBS_AUDIT_EVENTS,
        {
            "brand_id": brand_id,
            "tenant_id": "tenant-a",
            "event_type": "legacy",
            "actor_id": "owner",
            "details": "historic",
            "occurred_at": "2026-01-01T00:00:00+00:00",
        },
    )
    saved = await m.set_brand_membership(
        owner,
        SetBrandMembershipParams(
            brand_id=brand_id, user_id="editor", role="editor", expected_workspace_version=version
        ),
    )
    assert saved.status == "success"
