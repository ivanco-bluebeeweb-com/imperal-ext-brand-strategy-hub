"""P0 sealed VBS audit integrity tests."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from imperal_sdk.testing import MockContext

import main as m
from schemas import (
    CreateBrandProfileParams,
    InitializeVisualBrandWorkspaceParams,
    VerifyVisualBrandAuditIntegrityParams,
)


async def _workspace(ctx):
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Audit integrity brand"))
    initialized = await m.initialize_visual_brand_workspace(
        ctx, InitializeVisualBrandWorkspaceParams(brand_id=brand.data.id, confirm_owner_claim=True)
    )
    assert initialized.status == "success"
    return brand.data.id


@pytest.mark.asyncio
async def test_sealed_audit_events_verify_and_tampering_is_detected():
    ctx = MockContext(user_id="owner", tenant_id="tenant-a")
    brand_id = await _workspace(ctx)

    verified = await m.verify_visual_brand_audit_integrity(
        ctx, VerifyVisualBrandAuditIntegrityParams(brand_id=brand_id)
    )
    assert verified.status == "success"
    assert verified.data.valid is True
    assert verified.data.sealed_events >= 1
    assert verified.data.chained_events >= 1
    assert verified.data.chain_sequence == verified.data.chained_events
    assert len(verified.data.chain_head) == 64

    page = await ctx.store.query(m.VBS_AUDIT_EVENTS, where={"brand_id": brand_id}, limit=20)
    event = page.data[0]
    await ctx.store.update(m.VBS_AUDIT_EVENTS, event.id, {**event.data, "details": "tampered"})

    tampered = await m.verify_visual_brand_audit_integrity(
        ctx, VerifyVisualBrandAuditIntegrityParams(brand_id=brand_id)
    )
    assert tampered.status == "success"
    assert tampered.data.valid is False
    assert tampered.data.first_invalid_event_id == event.id


@pytest.mark.asyncio
async def test_unsealed_historical_audit_events_are_reported_as_legacy_not_validated():
    ctx = MockContext(user_id="owner", tenant_id="tenant-a")
    brand_id = await _workspace(ctx)
    await ctx.store.create(
        m.VBS_AUDIT_EVENTS,
        {
            "brand_id": brand_id,
            "tenant_id": "tenant-a",
            "event_type": "legacy_event",
            "actor_id": "owner",
            "details": "Predates integrity sealing.",
            "occurred_at": "2026-01-01T00:00:00+00:00",
        },
    )

    verified = await m.verify_visual_brand_audit_integrity(
        ctx, VerifyVisualBrandAuditIntegrityParams(brand_id=brand_id)
    )
    assert verified.status == "success"
    assert verified.data.valid is True
    assert verified.data.checked_events == verified.data.sealed_events + 1
    assert "legacy event" in verified.data.message


async def _chained_events(ctx, brand_id):
    page = await ctx.store.query(m.VBS_AUDIT_EVENTS, where={"brand_id": brand_id}, order_by="occurred_at", limit=20)
    return [item for item in page.data if item.data.get("integrity_version") == 2]


@pytest.mark.asyncio
async def test_audit_chain_detects_deleted_middle_and_tail_events_from_workspace_anchor():
    ctx = MockContext(user_id="owner", tenant_id="tenant-a")
    brand_id = await _workspace(ctx)

    # Create two more chained entries so a genuine middle and tail exist.
    await m._append_vbs_audit(ctx, brand_id=brand_id, vbs_id="", event_type="chain_test_one", details="First chain test event")
    await m._append_vbs_audit(ctx, brand_id=brand_id, vbs_id="", event_type="chain_test_two", details="Second chain test event")
    events = await _chained_events(ctx, brand_id)
    assert len(events) >= 3

    await ctx.store.delete(m.VBS_AUDIT_EVENTS, events[1].id)
    missing_middle = await m.verify_visual_brand_audit_integrity(
        ctx, VerifyVisualBrandAuditIntegrityParams(brand_id=brand_id)
    )
    assert missing_middle.data.valid is False

    # Isolate tail deletion in a fresh workspace: only the workspace anchor can reveal it.
    other = MockContext(user_id="owner", tenant_id="tenant-b")
    other_brand_id = await _workspace(other)
    await m._append_vbs_audit(other, brand_id=other_brand_id, vbs_id="", event_type="chain_tail", details="Tail chain test event")
    other_events = await _chained_events(other, other_brand_id)
    await other.store.delete(m.VBS_AUDIT_EVENTS, other_events[-1].id)
    missing_tail = await m.verify_visual_brand_audit_integrity(
        other, VerifyVisualBrandAuditIntegrityParams(brand_id=other_brand_id)
    )
    assert missing_tail.data.valid is False
    assert "anchor" in missing_tail.data.message


@pytest.mark.asyncio
async def test_audit_chain_detects_sequence_or_previous_hash_tampering():
    ctx = MockContext(user_id="owner", tenant_id="tenant-a")
    brand_id = await _workspace(ctx)
    await m._append_vbs_audit(ctx, brand_id=brand_id, vbs_id="", event_type="chain_test", details="Chain sequence test")
    event = (await _chained_events(ctx, brand_id))[-1]
    await ctx.store.update(
        m.VBS_AUDIT_EVENTS,
        event.id,
        {**event.data, "chain_sequence": 99, "previous_integrity_hash": "forged"},
    )

    verified = await m.verify_visual_brand_audit_integrity(
        ctx, VerifyVisualBrandAuditIntegrityParams(brand_id=brand_id)
    )
    assert verified.data.valid is False
    assert verified.data.first_invalid_event_id == event.id
