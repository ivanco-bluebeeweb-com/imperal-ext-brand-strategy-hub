"""P0 explicit migration from legacy VBS owner fields to membership ACL."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from imperal_sdk.testing import MockContext

import main as m
from schemas import (
    CreateBrandProfileParams,
    ListBrandMembershipsParams,
    ListVisualBrandAuditEventsParams,
    ListVisualBrandSystemsParams,
    MigrateVisualBrandAccessParams,
)


async def _legacy_workspace(ctx):
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Legacy VBS brand"))
    workspace = await ctx.store.create(
        m.VBS_WORKSPACES,
        {
            "brand_id": brand.data.id,
            "tenant_id": "tenant-a",
            "owner_id": "owner",
            "version": 7,
            "status": "ready",
            "created_at": "2026-01-01T00:00:00+00:00",
        },
    )
    system = await ctx.store.create(
        m.VBS_SYSTEMS,
        {
            "brand_id": brand.data.id,
            "tenant_id": "tenant-a",
            "revision": 1,
            "status": "approved_current",
            "visual_intent": "Preserve this legacy baseline",
        },
    )
    evidence = await ctx.store.create(
        m.VBS_EVIDENCE,
        {
            "brand_id": brand.data.id,
            "tenant_id": "tenant-a",
            "status": "reviewed_valid",
            "source_url": "https://example.org/legacy",
            "observation": "Existing reference",
        },
    )
    return brand.data.id, workspace, system, evidence


@pytest.mark.asyncio
async def test_explicit_legacy_membership_migration_is_idempotent_and_preserves_content():
    owner = MockContext(user_id="owner", tenant_id="tenant-a")
    brand_id, workspace, system, evidence = await _legacy_workspace(owner)

    before = await m.list_visual_brand_systems(owner, ListVisualBrandSystemsParams(brand_id=brand_id))
    assert before.status == "error"
    assert before.error_code == "VBS_ACCESS_DENIED"

    migrated = await m.migrate_visual_brand_access(
        owner, MigrateVisualBrandAccessParams(brand_id=brand_id, expected_workspace_version=7)
    )
    assert migrated.status == "success"
    assert migrated.data.access_model_version == 2
    assert migrated.data.version == 8

    memberships = await m.list_brand_memberships(owner, ListBrandMembershipsParams(brand_id=brand_id))
    assert [(item.user_id, item.role) for item in memberships.data.items] == [("owner", "owner")]
    after = await m.list_visual_brand_systems(owner, ListVisualBrandSystemsParams(brand_id=brand_id))
    assert after.status == "success"
    assert after.data.items[0].id == system.id
    stored_evidence = await owner.store.get(m.VBS_EVIDENCE, evidence.id)
    assert stored_evidence.data["status"] == "reviewed_valid"

    repeated = await m.migrate_visual_brand_access(
        owner, MigrateVisualBrandAccessParams(brand_id=brand_id, expected_workspace_version=8)
    )
    assert repeated.status == "success"
    assert repeated.data.version == 8
    memberships_again = await m.list_brand_memberships(owner, ListBrandMembershipsParams(brand_id=brand_id))
    assert len(memberships_again.data.items) == 1
    audit = await m.list_visual_brand_audit_events(owner, ListVisualBrandAuditEventsParams(brand_id=brand_id))
    assert [item.event_type for item in audit.data.items].count("membership_model_migrated") == 1


@pytest.mark.asyncio
async def test_legacy_migration_blocks_cross_tenant_and_stale_attempts():
    owner = MockContext(user_id="owner", tenant_id="tenant-a")
    outsider = MockContext(user_id="owner", tenant_id="tenant-b")
    outsider.store = owner.store
    brand_id, _workspace, _system, _evidence = await _legacy_workspace(owner)

    denied = await m.migrate_visual_brand_access(
        outsider, MigrateVisualBrandAccessParams(brand_id=brand_id, expected_workspace_version=7)
    )
    assert denied.status == "error"
    assert denied.error_code == "VBS_ACCESS_DENIED"
    stale = await m.migrate_visual_brand_access(
        owner, MigrateVisualBrandAccessParams(brand_id=brand_id, expected_workspace_version=6)
    )
    assert stale.status == "error"
    assert stale.error_code == "VBS_STALE_WORKSPACE"
