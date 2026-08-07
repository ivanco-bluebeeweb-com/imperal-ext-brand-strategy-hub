"""P1 read-only handoff tests for an approved, integrity-verified Visual Profile."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from imperal_sdk.testing import MockContext

import main as m
from schemas import (
    ActivateVisualBrandSystemParams,
    ActivateVisualProfileParams,
    BuildApprovedVisualProfileHandoffParams,
    CreateBrandProfileParams,
    CreateVisualBrandSystemParams,
    CreateVisualProfileParams,
    InitializeVisualBrandWorkspaceParams,
)


async def _brand_workspace_and_current_vbs(ctx):
    brand = await m.create_brand_profile(
        ctx, CreateBrandProfileParams(brand_name="Visual handoff brand")
    )
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
async def test_approved_visual_profile_handoff_exports_only_current_nonpersonal_baseline():
    ctx = MockContext(user_id="owner", tenant_id="tenant-a")
    brand_id, version = await _brand_workspace_and_current_vbs(ctx)
    draft = await m.create_visual_profile(
        ctx,
        CreateVisualProfileParams(
            brand_id=brand_id,
            expected_workspace_version=version,
            profile_summary="Practical, non-personal operational visual baseline.",
            art_direction="Grounded documentary realism; no synthetic people.",
        ),
    )
    approved = await m.activate_visual_profile(
        ctx,
        ActivateVisualProfileParams(
            profile_id=draft.data["profile_id"],
            expected_revision=1,
            expected_workspace_version=draft.data["workspace_version"],
            approval_note="Approved for downstream content planning.",
        ),
    )
    assert approved.status == "success"

    handoff = await m.build_approved_visual_profile_handoff(
        ctx, BuildApprovedVisualProfileHandoffParams(brand_id=brand_id)
    )
    assert handoff.status == "success"
    assert handoff.data.profile_id == draft.data["profile_id"]
    assert handoff.data.profile_revision == 1
    assert handoff.data.vbs_revision == 1
    assert handoff.data.profile_summary == "Practical, non-personal operational visual baseline."
    assert handoff.data.art_direction == "Grounded documentary realism; no synthetic people."
    assert handoff.data.snapshot_hash


@pytest.mark.asyncio
async def test_visual_profile_handoff_requires_approved_profile_and_is_tenant_local():
    owner = MockContext(user_id="owner", tenant_id="tenant-a")
    outsider = MockContext(user_id="outsider", tenant_id="tenant-b")
    outsider.store = owner.store
    brand_id, version = await _brand_workspace_and_current_vbs(owner)

    missing = await m.build_approved_visual_profile_handoff(
        owner, BuildApprovedVisualProfileHandoffParams(brand_id=brand_id)
    )
    assert missing.status == "error"
    assert missing.error_code == "VISUAL_PROFILE_CURRENT_REQUIRED"

    denied = await m.build_approved_visual_profile_handoff(
        outsider, BuildApprovedVisualProfileHandoffParams(brand_id=brand_id)
    )
    assert denied.status == "error"
    assert denied.error_code == "VBS_ACCESS_DENIED"

    # A draft alone must not become a downstream baseline.
    draft = await m.create_visual_profile(
        owner,
        CreateVisualProfileParams(
            brand_id=brand_id,
            expected_workspace_version=version,
            profile_summary="Still a draft.",
        ),
    )
    assert draft.status == "success"
    still_missing = await m.build_approved_visual_profile_handoff(
        owner, BuildApprovedVisualProfileHandoffParams(brand_id=brand_id)
    )
    assert still_missing.status == "error"
    assert still_missing.error_code == "VISUAL_PROFILE_CURRENT_REQUIRED"
