"""P0 Visual Profile tests: immutable baseline resolution, hash and private ACL."""
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
    ListVisualProfilesParams,
    RegisterVisualEvidenceParams,
    ReviewVisualEvidenceParams,
    ResolveCurrentVisualProfileParams,
)


async def _brand_workspace_and_current_vbs(ctx):
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Profile baseline brand"))
    brand_id = brand.data.id
    await m.initialize_visual_brand_workspace(
        ctx, InitializeVisualBrandWorkspaceParams(brand_id=brand_id, confirm_owner_claim=True)
    )
    draft = await m.create_visual_brand_system(
        ctx,
        CreateVisualBrandSystemParams(
            brand_id=brand_id,
            expected_workspace_version=1,
            visual_intent="Grounded operational confidence",
            core_rules=["Show real working environments"],
        ),
    )
    approved = await m.activate_visual_brand_system(
        ctx,
        ActivateVisualBrandSystemParams(
            vbs_id=draft.data["vbs_id"], expected_revision=1, expected_workspace_version=2
        ),
    )
    assert approved.status == "success"
    return brand_id, approved.data["workspace_version"]


@pytest.mark.asyncio
async def test_profile_requires_current_vbs_then_resolves_immutable_snapshot():
    ctx = MockContext(user_id="owner", tenant_id="tenant-a")
    brand_id, version = await _brand_workspace_and_current_vbs(ctx)
    evidence = await m.register_visual_evidence(
        ctx,
        RegisterVisualEvidenceParams(
            brand_id=brand_id,
            expected_workspace_version=version,
            source_url="https://example.com/baseline",
            observation="Supports evidence-led operational visuals.",
        ),
    )
    reviewed = await m.review_visual_evidence(
        ctx,
        ReviewVisualEvidenceParams(
            evidence_id=evidence.data["id"],
            expected_status="discovered",
            expected_workspace_version=evidence.data["workspace_version"],
            decision="reviewed_valid",
            review_note="Eligible for the profile baseline.",
        ),
    )
    assert reviewed.status == "success"
    profile = await m.create_visual_profile(
        ctx,
        CreateVisualProfileParams(
            brand_id=brand_id,
            expected_workspace_version=reviewed.data.workspace_version,
            evidence_ids=[evidence.data["id"]],
            profile_summary="Documentary-feeling visual language for operational trust.",
            art_direction="Grounded light, real environments, no stock staging.",
        ),
    )
    assert profile.status == "success"
    assert len(profile.data["snapshot_hash"]) == 64

    before_approval = await m.resolve_current_visual_profile(
        ctx, ResolveCurrentVisualProfileParams(brand_id=brand_id)
    )
    assert before_approval.status == "error"
    assert before_approval.error_code == "VISUAL_PROFILE_CURRENT_REQUIRED"

    approved = await m.activate_visual_profile(
        ctx,
        ActivateVisualProfileParams(
            profile_id=profile.data["profile_id"],
            expected_revision=1,
            expected_workspace_version=profile.data["workspace_version"],
        ),
    )
    assert approved.status == "success"
    resolved = await m.resolve_current_visual_profile(ctx, ResolveCurrentVisualProfileParams(brand_id=brand_id))
    assert resolved.status == "success"
    assert resolved.data.snapshot_hash == profile.data["snapshot_hash"]
    assert resolved.data.vbs_revision == 1


@pytest.mark.asyncio
async def test_profile_access_and_stale_vbs_baseline_fail_closed():
    owner = MockContext(user_id="owner", tenant_id="tenant-a")
    brand_id, version = await _brand_workspace_and_current_vbs(owner)
    profile = await m.create_visual_profile(
        owner,
        CreateVisualProfileParams(
            brand_id=brand_id,
            expected_workspace_version=version,
            profile_summary="First non-personal profile baseline.",
        ),
    )
    await m.activate_visual_profile(
        owner,
        ActivateVisualProfileParams(
            profile_id=profile.data["profile_id"],
            expected_revision=1,
            expected_workspace_version=profile.data["workspace_version"],
        ),
    )

    other = MockContext(user_id="other", tenant_id="tenant-a")
    other.store = owner.store
    denied = await m.list_visual_profiles(other, ListVisualProfilesParams(brand_id=brand_id))
    assert denied.status == "error"
    assert denied.error_code == "VBS_ACCESS_DENIED"

    vbs2 = await m.create_visual_brand_system(
        owner,
        CreateVisualBrandSystemParams(
            brand_id=brand_id,
            expected_workspace_version=profile.data["workspace_version"] + 1,
            visual_intent="Updated baseline invalidates prior profile resolution.",
        ),
    )
    assert vbs2.status == "success"
    activation = await m.activate_visual_brand_system(
        owner,
        ActivateVisualBrandSystemParams(
            vbs_id=vbs2.data["vbs_id"],
            expected_revision=2,
            expected_workspace_version=vbs2.data["workspace_version"],
        ),
    )
    assert activation.status == "success"
    stale = await m.resolve_current_visual_profile(owner, ResolveCurrentVisualProfileParams(brand_id=brand_id))
    assert stale.status == "error"
    assert stale.error_code == "VISUAL_PROFILE_BASELINE_STALE"


@pytest.mark.asyncio
async def test_profile_approval_rejects_a_draft_bound_to_a_superseded_vbs():
    ctx = MockContext(user_id="owner", tenant_id="tenant-a")
    brand_id, version = await _brand_workspace_and_current_vbs(ctx)
    profile = await m.create_visual_profile(
        ctx,
        CreateVisualProfileParams(
            brand_id=brand_id,
            expected_workspace_version=version,
            profile_summary="Profile draft bound to VBS revision one.",
        ),
    )
    replacement = await m.create_visual_brand_system(
        ctx,
        CreateVisualBrandSystemParams(
            brand_id=brand_id,
            expected_workspace_version=profile.data["workspace_version"],
            visual_intent="Replacement VBS baseline.",
        ),
    )
    activated = await m.activate_visual_brand_system(
        ctx,
        ActivateVisualBrandSystemParams(
            vbs_id=replacement.data["vbs_id"],
            expected_revision=2,
            expected_workspace_version=replacement.data["workspace_version"],
        ),
    )
    rejected = await m.activate_visual_profile(
        ctx,
        ActivateVisualProfileParams(
            profile_id=profile.data["profile_id"],
            expected_revision=1,
            expected_workspace_version=activated.data["workspace_version"],
        ),
    )

    assert rejected.status == "error"
    assert rejected.error_code == "VISUAL_PROFILE_BASELINE_STALE"
    listed = await m.list_visual_profiles(ctx, ListVisualProfilesParams(brand_id=brand_id))
    assert listed.data.items[0].status == "draft"
