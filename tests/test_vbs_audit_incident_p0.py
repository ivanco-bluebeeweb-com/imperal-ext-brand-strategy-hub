"""P0 owner acknowledgement for VBS audit-integrity incidents."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from imperal_sdk.testing import MockContext

import main as m
from schemas import (
    AcknowledgeVisualBrandAuditIncidentParams,
    CreateBrandProfileParams,
    InitializeVisualBrandWorkspaceParams,
    ListVisualBrandAuditIncidentsParams,
    SetBrandMembershipParams,
)


async def _workspace(ctx):
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Incident acknowledgement brand"))
    initialized = await m.initialize_visual_brand_workspace(
        ctx, InitializeVisualBrandWorkspaceParams(brand_id=brand.data.id, confirm_owner_claim=True)
    )
    return brand.data.id, initialized.data["version"]


async def _tamper(ctx, brand_id):
    page = await ctx.store.query(m.VBS_AUDIT_EVENTS, where={"brand_id": brand_id}, limit=20)
    event = next(item for item in page.data if item.data.get("integrity_hash"))
    await ctx.store.update(m.VBS_AUDIT_EVENTS, event.id, {**event.data, "details": "tampered"})
    return event.id


@pytest.mark.asyncio
async def test_owner_acknowledgement_is_idempotent_and_does_not_clear_integrity_gate():
    owner = MockContext(user_id="owner", tenant_id="tenant-a")
    brand_id, version = await _workspace(owner)
    invalid_event_id = await _tamper(owner, brand_id)

    acknowledged = await m.acknowledge_visual_brand_audit_incident(
        owner,
        AcknowledgeVisualBrandAuditIncidentParams(
            brand_id=brand_id,
            expected_workspace_version=version,
            acknowledgement_note="Reviewed the mismatch and retained the safety block.",
        ),
    )
    assert acknowledged.status == "success"
    assert acknowledged.data.invalid_event_id == invalid_event_id

    again = await m.acknowledge_visual_brand_audit_incident(
        owner,
        AcknowledgeVisualBrandAuditIncidentParams(
            brand_id=brand_id,
            expected_workspace_version=version,
            acknowledgement_note="Second submission should not duplicate the incident.",
        ),
    )
    assert again.status == "success"
    assert again.data.id == acknowledged.data.id

    incidents = await owner.store.query(m.VBS_AUDIT_INCIDENTS, where={"brand_id": brand_id}, limit=20)
    assert len(incidents.data) == 1
    blocked = await m.set_brand_membership(
        owner,
        SetBrandMembershipParams(brand_id=brand_id, user_id="editor", role="editor", expected_workspace_version=version),
    )
    assert blocked.status == "error"
    assert blocked.error_code == "VBS_AUDIT_INTEGRITY_FAILED"

    listed = await m.list_visual_brand_audit_incidents(
        owner, ListVisualBrandAuditIncidentsParams(brand_id=brand_id)
    )
    assert listed.status == "success"
    assert len(listed.data.items) == 1
    assert listed.data.items[0].invalid_event_id == invalid_event_id


@pytest.mark.asyncio
async def test_only_owner_can_acknowledge_an_integrity_incident():
    owner = MockContext(user_id="owner", tenant_id="tenant-a")
    editor = MockContext(user_id="editor", tenant_id="tenant-a")
    editor.store = owner.store
    brand_id, version = await _workspace(owner)
    granted = await m.set_brand_membership(
        owner,
        SetBrandMembershipParams(brand_id=brand_id, user_id="editor", role="editor", expected_workspace_version=version),
    )
    await _tamper(owner, brand_id)

    denied = await m.acknowledge_visual_brand_audit_incident(
        editor,
        AcknowledgeVisualBrandAuditIncidentParams(
            brand_id=brand_id,
            expected_workspace_version=granted.data.workspace_version,
            acknowledgement_note="Editor cannot acknowledge this incident.",
        ),
    )
    assert denied.status == "error"
    assert denied.error_code == "VBS_ACCESS_DENIED"
