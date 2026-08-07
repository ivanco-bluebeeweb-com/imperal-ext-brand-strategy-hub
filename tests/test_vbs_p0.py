"""P0 VBS vertical-slice tests: private workspace, revisions and manual UI spike."""
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
    ListVisualBrandAuditEventsParams,
    ListVisualBrandSystemsParams,
    RegisterVisualEvidenceParams,
    ReviewVisualEvidenceParams,
)


async def _brand(ctx):
    result = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="G4S Moldova"))
    return result.data.id


async def _workspace(ctx, brand_id):
    return await m.initialize_visual_brand_workspace(
        ctx, InitializeVisualBrandWorkspaceParams(brand_id=brand_id, confirm_owner_claim=True)
    )


@pytest.mark.asyncio
async def test_vbs_workspace_requires_explicit_owner_claim():
    ctx = MockContext()
    brand_id = await _brand(ctx)

    result = await m.initialize_visual_brand_workspace(
        ctx, InitializeVisualBrandWorkspaceParams(brand_id=brand_id, confirm_owner_claim=False)
    )

    assert result.status == "error"
    assert result.error_code == "VBS_OWNER_CLAIM_REQUIRED"


@pytest.mark.asyncio
async def test_vbs_workspace_is_private_to_authenticated_owner_and_tenant():
    owner = MockContext(user_id="owner", tenant_id="tenant-a")
    brand_id = await _brand(owner)
    initialized = await _workspace(owner, brand_id)
    assert initialized.status == "success"

    other = MockContext(user_id="another_user", tenant_id="tenant-a")
    other.store = owner.store

    result = await m.list_visual_brand_systems(other, ListVisualBrandSystemsParams(brand_id=brand_id))
    assert result.status == "error"
    assert result.error_code == "VBS_ACCESS_DENIED"


@pytest.mark.asyncio
async def test_vbs_draft_is_versioned_and_stale_workspace_write_is_rejected():
    ctx = MockContext()
    brand_id = await _brand(ctx)
    await _workspace(ctx, brand_id)

    created = await m.create_visual_brand_system(
        ctx,
        CreateVisualBrandSystemParams(
            brand_id=brand_id,
            expected_workspace_version=1,
            visual_intent="Make security work feel real and dependable",
            realism_level="grounded realism",
            core_rules=["Use real working environments"],
            prohibited_patterns=["Glossy stock-smile scenes"],
        ),
    )
    assert created.status == "success"
    assert created.data["revision"] == 1
    assert created.data["status"] == "draft"

    stale = await m.create_visual_brand_system(
        ctx,
        CreateVisualBrandSystemParams(
            brand_id=brand_id,
            expected_workspace_version=1,
            visual_intent="This request used an old workspace view",
        ),
    )
    assert stale.status == "error"
    assert stale.error_code == "VBS_STALE_WORKSPACE"


@pytest.mark.asyncio
async def test_vbs_approval_makes_one_revision_current_and_preserves_audit():
    ctx = MockContext()
    brand_id = await _brand(ctx)
    await _workspace(ctx, brand_id)
    first = await m.create_visual_brand_system(
        ctx,
        CreateVisualBrandSystemParams(
            brand_id=brand_id,
            expected_workspace_version=1,
            visual_intent="Grounded visual proof",
        ),
    )

    approved = await m.activate_visual_brand_system(
        ctx,
        ActivateVisualBrandSystemParams(
            vbs_id=first.data["vbs_id"],
            expected_revision=1,
            expected_workspace_version=2,
            approval_note="Initial baseline approved",
        ),
    )
    assert approved.status == "success"
    assert approved.data["status"] == "approved_current"
    assert approved.data["workspace_version"] == 3

    revisions = await m.list_visual_brand_systems(ctx, ListVisualBrandSystemsParams(brand_id=brand_id))
    assert revisions.status == "success"
    assert len(revisions.data.items) == 1
    assert revisions.data.items[0].status == "approved_current"

    audit = await m.list_visual_brand_audit_events(
        ctx, ListVisualBrandAuditEventsParams(brand_id=brand_id)
    )
    assert audit.status == "success"
    event_types = {event.event_type for event in audit.data.items}
    assert {"workspace_initialized", "vbs_draft_created", "vbs_approved_current"} <= event_types


@pytest.mark.asyncio
async def test_vbs_approval_rejects_a_stale_workspace_snapshot():
    ctx = MockContext()
    brand_id = await _brand(ctx)
    await _workspace(ctx, brand_id)
    first = await m.create_visual_brand_system(
        ctx,
        CreateVisualBrandSystemParams(
            brand_id=brand_id,
            expected_workspace_version=1,
            visual_intent="Grounded visual proof",
        ),
    )

    stale = await m.activate_visual_brand_system(
        ctx,
        ActivateVisualBrandSystemParams(
            vbs_id=first.data["vbs_id"],
            expected_revision=1,
            expected_workspace_version=1,
        ),
    )

    assert stale.status == "error"
    assert stale.error_code == "VBS_STALE_WORKSPACE"
    revisions = await m.list_visual_brand_systems(ctx, ListVisualBrandSystemsParams(brand_id=brand_id))
    assert revisions.data.items[0].status == "draft"


@pytest.mark.asyncio
async def test_visual_system_panel_has_safe_empty_and_owned_workspace_states():
    ctx = MockContext()
    brand_id = await _brand(ctx)

    uninitialized = await m.brand_detail_panel(ctx, brand_id=brand_id, tab="visual_system")
    rendered_uninitialized = repr(uninitialized)
    assert "VBS workspace not initialized" in rendered_uninitialized
    assert "Visual System" in rendered_uninitialized
    assert "initialize_visual_brand_workspace" in rendered_uninitialized
    assert "I am the workspace owner — initialize" in rendered_uninitialized
    assert "confirm_owner_claim" in rendered_uninitialized

    await _workspace(ctx, brand_id)
    evidence = await m.register_visual_evidence(
        ctx,
        RegisterVisualEvidenceParams(
            brand_id=brand_id,
            expected_workspace_version=1,
            source_url="https://example.com/ui-review",
            observation="A reference used to validate the manual review UI.",
        ),
    )
    assert evidence.status == "success"
    initialized = await m.brand_detail_panel(ctx, brand_id=brand_id, tab="visual_system")
    rendered = repr(initialized)
    assert "Create next VBS draft" in rendered
    assert "None" not in rendered
    assert "create_visual_brand_system" in rendered
    assert "expected_workspace_version" in rendered
    assert "Register evidence reference" in rendered
    assert "register_visual_evidence" in rendered
    assert "never fetches, downloads or processes the source" in rendered
    assert "review_visual_evidence" in rendered
    assert "Save review decision" in rendered
    assert "expected_status" in rendered
    assert "Create Visual Profile draft" in rendered
    assert "Private workspace access" in rendered
    assert "set_brand_membership" in rendered
    assert "Known Imperal user ID" in rendered
    assert "Editor access and approved VBS required" in rendered
    assert "Audit trail" in rendered
    assert "People/media" in rendered
    assert "Blocked pending privacy/storage spikes" in rendered

    reviewed = await m.review_visual_evidence(
        ctx,
        ReviewVisualEvidenceParams(
            evidence_id=evidence.data["id"],
            expected_status="discovered",
            expected_workspace_version=evidence.data["workspace_version"],
            decision="reviewed_valid",
            review_note="Reviewed for profile UI selection.",
        ),
    )
    draft = await m.create_visual_brand_system(
        ctx,
        CreateVisualBrandSystemParams(
            brand_id=brand_id,
            expected_workspace_version=reviewed.data.workspace_version,
            visual_intent="Clear and grounded proof.",
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

    with_current_vbs = await m.brand_detail_panel(ctx, brand_id=brand_id, tab="visual_system")
    rendered_current = repr(with_current_vbs)
    assert "Approved VBS" in rendered_current
    assert "Revision 1" in rendered_current
    assert "reviewed-valid reference(s) · verified" in rendered_current
    assert "Choose reviewed-valid evidence ID" in rendered_current
    assert evidence.data["id"] in rendered_current
    assert "Only reviewed-valid references from this private workspace are offered" in rendered_current

    assert "create_visual_profile" in rendered_current
    assert "Save profile draft" in rendered_current
    assert "expected_workspace_version" in rendered_current
    assert "Visual Profiles" in rendered_current
