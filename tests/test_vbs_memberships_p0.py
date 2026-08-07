"""P0 VBS membership and role-based authorization tests."""
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
    ListBrandMembershipsParams,
    ListVisualBrandSystemsParams,
    RegisterVisualEvidenceParams,
    RevokeBrandMembershipParams,
    SetBrandMembershipParams,
)


async def _workspace(owner):
    brand = await m.create_brand_profile(owner, CreateBrandProfileParams(brand_name="Membership test brand"))
    brand_id = brand.data.id
    initialized = await m.initialize_visual_brand_workspace(
        owner, InitializeVisualBrandWorkspaceParams(brand_id=brand_id, confirm_owner_claim=True)
    )
    assert initialized.status == "success"
    return brand_id, initialized.data["version"]


@pytest.mark.asyncio
async def test_roles_are_enforced_server_side_and_membership_is_tenant_local():
    owner = MockContext(user_id="owner", tenant_id="tenant-a")
    editor = MockContext(user_id="editor", tenant_id="tenant-a")
    reviewer = MockContext(user_id="reviewer", tenant_id="tenant-a")
    viewer = MockContext(user_id="viewer", tenant_id="tenant-a")
    outsider = MockContext(user_id="outsider", tenant_id="tenant-b")
    for member_ctx in (editor, reviewer, viewer, outsider):
        member_ctx.store = owner.store
    brand_id, version = await _workspace(owner)

    for user_id, role in (("editor", "editor"), ("reviewer", "reviewer"), ("viewer", "viewer")):
        saved = await m.set_brand_membership(
            owner, SetBrandMembershipParams(brand_id=brand_id, user_id=user_id, role=role, expected_workspace_version=version)
        )
        assert saved.status == "success"
        version += 1

    draft = await m.create_visual_brand_system(
        editor,
        CreateVisualBrandSystemParams(brand_id=brand_id, expected_workspace_version=version, visual_intent="Grounded visual direction"),
    )
    assert draft.status == "success"

    editor_approval = await m.activate_visual_brand_system(
        editor,
        ActivateVisualBrandSystemParams(
            vbs_id=draft.data["vbs_id"], expected_revision=1, expected_workspace_version=draft.data["workspace_version"]
        ),
    )
    assert editor_approval.status == "error"
    assert editor_approval.error_code == "VBS_ACCESS_DENIED"

    approved = await m.activate_visual_brand_system(
        reviewer,
        ActivateVisualBrandSystemParams(
            vbs_id=draft.data["vbs_id"], expected_revision=1, expected_workspace_version=draft.data["workspace_version"]
        ),
    )
    assert approved.status == "success"

    viewer_read = await m.list_visual_brand_systems(viewer, ListVisualBrandSystemsParams(brand_id=brand_id))
    assert viewer_read.status == "success"
    viewer_write = await m.register_visual_evidence(
        viewer,
        RegisterVisualEvidenceParams(
            brand_id=brand_id,
            expected_workspace_version=approved.data["workspace_version"],
            source_url="https://example.com/blocked",
            observation="Viewer must not write.",
        ),
    )
    assert viewer_write.status == "error"
    assert viewer_write.error_code == "VBS_ACCESS_DENIED"

    cross_tenant = await m.list_brand_memberships(outsider, ListBrandMembershipsParams(brand_id=brand_id))
    assert cross_tenant.status == "error"
    assert cross_tenant.error_code == "VBS_ACCESS_DENIED"

    viewer_panel = await m.brand_detail_panel(viewer, brand_id=brand_id, tab="visual_system")
    rendered_viewer = repr(viewer_panel)
    assert "Editor access required" in rendered_viewer
    assert "Save review decision" not in rendered_viewer
    assert "Approve as current" not in rendered_viewer
    assert "Save profile draft" not in rendered_viewer


@pytest.mark.asyncio
async def test_only_owner_manages_memberships_and_founding_owner_is_protected():
    owner = MockContext(user_id="owner", tenant_id="tenant-a")
    editor = MockContext(user_id="editor", tenant_id="tenant-a")
    editor.store = owner.store
    brand_id, version = await _workspace(owner)
    added = await m.set_brand_membership(
        owner, SetBrandMembershipParams(brand_id=brand_id, user_id="editor", role="editor", expected_workspace_version=version)
    )
    assert added.status == "success"

    editor_change = await m.set_brand_membership(
        editor,
        SetBrandMembershipParams(brand_id=brand_id, user_id="viewer", role="viewer", expected_workspace_version=added.data.workspace_version),
    )
    assert editor_change.status == "error"
    assert editor_change.error_code == "VBS_ACCESS_DENIED"

    demote_founding_owner = await m.set_brand_membership(
        owner,
        SetBrandMembershipParams(brand_id=brand_id, user_id="owner", role="viewer", expected_workspace_version=added.data.workspace_version),
    )
    assert demote_founding_owner.status == "error"
    assert demote_founding_owner.error_code == "VBS_LAST_OWNER_PROTECTED"

    revoke_founding_owner = await m.revoke_brand_membership(
        owner,
        RevokeBrandMembershipParams(brand_id=brand_id, user_id="owner", expected_workspace_version=added.data.workspace_version),
    )
    assert revoke_founding_owner.status == "error"
    assert revoke_founding_owner.error_code == "VBS_LAST_OWNER_PROTECTED"
