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
