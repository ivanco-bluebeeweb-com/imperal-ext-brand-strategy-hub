"""P2-A tests: human-recorded media conformance verdicts against the approved
Visual Profile. No generation, no fetch, no personal imagery involved."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from imperal_sdk.testing import MockContext

import main as m
from schemas import (
    ActivateVisualBrandSystemParams,
    ActivateVisualProfileParams,
    CreateBrandProfileParams,
    CreateVisualBrandSystemParams,
    CreateVisualProfileParams,
    InitializeVisualBrandWorkspaceParams,
    ListMediaConformanceParams,
    RecordMediaConformanceParams,
    RegisterVisualEvidenceParams,
    ReviewVisualEvidenceParams,
    SetBrandMembershipParams,
)


async def _brand_with_approved_profile(ctx, brand_name="Conformance brand"):
    """Build a brand with a fully approved current VBS + Visual Profile."""
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name=brand_name))
    brand_id = brand.data.id
    await m.initialize_visual_brand_workspace(
        ctx, InitializeVisualBrandWorkspaceParams(brand_id=brand_id, confirm_owner_claim=True)
    )
    evidence = await m.register_visual_evidence(
        ctx,
        RegisterVisualEvidenceParams(
            brand_id=brand_id,
            expected_workspace_version=1,
            source_url="https://example.org/conformance-source",
            source_title="Conformance source",
            observation="Grounds the approved visual direction.",
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
            visual_intent="Clean, industrial, trustworthy.",
            realism_level="photorealistic",
            core_rules=["Blue/grey palette", "No stock-photo clichés"],
            prohibited_patterns=["No people's faces"],
            evidence_ids=[evidence.data["id"]],
        ),
    )
    activated = await m.activate_visual_brand_system(
        ctx,
        ActivateVisualBrandSystemParams(
            vbs_id=draft.data["vbs_id"],
            expected_revision=draft.data["revision"],
            expected_workspace_version=draft.data["workspace_version"],
            approval_note="Approved for conformance tests.",
        ),
    )
    profile_draft = await m.create_visual_profile(
        ctx,
        CreateVisualProfileParams(
            brand_id=brand_id,
            expected_workspace_version=activated.data["workspace_version"],
            evidence_ids=[evidence.data["id"]],
            profile_summary="Non-personal profile summary for conformance tests.",
            art_direction="Industrial, blue/grey.",
        ),
    )
    await m.activate_visual_profile(
        ctx,
        ActivateVisualProfileParams(
            profile_id=profile_draft.data["profile_id"],
            expected_revision=profile_draft.data["revision"],
            expected_workspace_version=profile_draft.data["workspace_version"],
            approval_note="Approved for conformance tests.",
        ),
    )
    return brand_id


@pytest.mark.asyncio
async def test_record_conformance_requires_review_permission_not_just_edit():
    ctx = MockContext(user_id="owner", tenant_id="tenant-a")
    brand_id = await _brand_with_approved_profile(ctx)
    workspace = await m._workspace_for_brand(ctx, brand_id)
    await m.set_brand_membership(
        ctx,
        SetBrandMembershipParams(brand_id=brand_id, user_id="editor-user", role="editor", expected_workspace_version=workspace.data["version"]),
    )

    ctx_editor = MockContext(user_id="editor-user", tenant_id="tenant-a")
    ctx_editor.store = ctx.store
    result = await m.record_media_conformance(
        ctx_editor,
        RecordMediaConformanceParams(
            brand_id=brand_id,
            media_package_id="pkg-123",
            verdict="conforms",
            reviewer_note="Checked visually against the approved guidance.",
        ),
    )
    assert result.status == "error"


@pytest.mark.asyncio
async def test_record_conformance_succeeds_for_reviewer_and_appends_audit():
    ctx = MockContext(user_id="owner", tenant_id="tenant-a")
    brand_id = await _brand_with_approved_profile(ctx)
    workspace = await m._workspace_for_brand(ctx, brand_id)
    await m.set_brand_membership(
        ctx,
        SetBrandMembershipParams(brand_id=brand_id, user_id="reviewer-user", role="reviewer", expected_workspace_version=workspace.data["version"]),
    )

    ctx_reviewer = MockContext(user_id="reviewer-user", tenant_id="tenant-a")
    ctx_reviewer.store = ctx.store
    result = await m.record_media_conformance(
        ctx_reviewer,
        RecordMediaConformanceParams(
            brand_id=brand_id,
            media_package_id="pkg-123",
            verdict="drifted",
            reviewer_note="Featured image used a warm palette, not the approved blue/grey.",
        ),
    )
    assert result.status == "success"
    assert result.data.verdict == "drifted"
    assert result.data.media_package_id == "pkg-123"
    assert result.data.profile_revision == 1
    assert result.data.snapshot_hash

    listed = await m.list_media_conformance(
        ctx_reviewer, ListMediaConformanceParams(brand_id=brand_id)
    )
    assert listed.status == "success"
    assert len(listed.data.items) == 1
    assert listed.data.items[0].verdict == "drifted"


@pytest.mark.asyncio
async def test_record_conformance_rejects_invalid_verdict():
    ctx = MockContext(user_id="owner", tenant_id="tenant-a")
    brand_id = await _brand_with_approved_profile(ctx)

    result = await m.record_media_conformance(
        ctx,
        RecordMediaConformanceParams(
            brand_id=brand_id,
            media_package_id="pkg-123",
            verdict="looks_fine_i_guess",
            reviewer_note="Not a real verdict value.",
        ),
    )
    assert result.status == "error"
    assert result.error_code == "VBS_CONFORMANCE_VERDICT_INVALID"


@pytest.mark.asyncio
async def test_record_conformance_requires_an_approved_current_profile():
    ctx = MockContext(user_id="owner", tenant_id="tenant-a")
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="No profile brand"))
    brand_id = brand.data.id
    await m.initialize_visual_brand_workspace(
        ctx, InitializeVisualBrandWorkspaceParams(brand_id=brand_id, confirm_owner_claim=True)
    )

    result = await m.record_media_conformance(
        ctx,
        RecordMediaConformanceParams(
            brand_id=brand_id,
            media_package_id="pkg-999",
            verdict="conforms",
            reviewer_note="No approved profile exists yet.",
        ),
    )
    assert result.status == "error"
    assert result.error_code == "VISUAL_PROFILE_CURRENT_REQUIRED"


@pytest.mark.asyncio
async def test_conformance_records_are_tenant_isolated():
    ctx_a = MockContext(user_id="owner-a", tenant_id="tenant-a")
    brand_id_a = await _brand_with_approved_profile(ctx_a, brand_name="Tenant A brand")
    await m.record_media_conformance(
        ctx_a,
        RecordMediaConformanceParams(
            brand_id=brand_id_a,
            media_package_id="pkg-a",
            verdict="conforms",
            reviewer_note="Matches for tenant A.",
        ),
    )

    ctx_b = MockContext(user_id="owner-b", tenant_id="tenant-b")
    result = await m.list_media_conformance(ctx_b, ListMediaConformanceParams(brand_id=brand_id_a))
    assert result.status == "error"
