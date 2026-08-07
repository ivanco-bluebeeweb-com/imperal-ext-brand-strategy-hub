"""P0 VBS evidence intake tests: private references, no-fetch URL policy and audit."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from imperal_sdk.testing import MockContext

import main as m
from schemas import (
    CreateBrandProfileParams,
    InitializeVisualBrandWorkspaceParams,
    ListVisualEvidenceParams,
    RegisterVisualEvidenceParams,
    ReviewVisualEvidenceParams,
)


async def _brand_and_workspace(ctx):
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Evidence test brand"))
    initialized = await m.initialize_visual_brand_workspace(
        ctx,
        InitializeVisualBrandWorkspaceParams(brand_id=brand.data.id, confirm_owner_claim=True),
    )
    assert initialized.status == "success"
    return brand.data.id


@pytest.mark.asyncio
async def test_evidence_registers_only_a_canonical_public_https_reference():
    ctx = MockContext(user_id="owner", tenant_id="tenant-a")
    brand_id = await _brand_and_workspace(ctx)

    result = await m.register_visual_evidence(
        ctx,
        RegisterVisualEvidenceParams(
            brand_id=brand_id,
            expected_workspace_version=1,
            source_url="HTTPS://Example.COM/research?source=VBS",
            source_title="Research summary",
            observation="The source supports a grounded, operational visual direction.",
        ),
    )

    assert result.status == "success"
    assert result.data["source_url"] == "https://example.com/research?source=VBS"
    assert result.data["status"] == "discovered"
    assert result.data["workspace_version"] == 2

    evidence = await m.list_visual_evidence(ctx, ListVisualEvidenceParams(brand_id=brand_id))
    assert evidence.status == "success"
    assert len(evidence.data.items) == 1
    assert evidence.data.items[0].source_url == "https://example.com/research?source=VBS"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_url",
    [
        "http://example.com/source",
        "https://localhost/source",
        "https://127.0.0.1/source",
        "https://10.0.0.8/source",
        "https://169.254.169.254/latest/meta-data",
        "https://[::1]/source",
        "https://example.com:8443/source",
        "https://user:password@example.com/source",
        "https://example.com/source#fragment",
    ],
)
async def test_evidence_rejects_non_public_or_unsafe_references(source_url):
    ctx = MockContext()
    brand_id = await _brand_and_workspace(ctx)

    result = await m.register_visual_evidence(
        ctx,
        RegisterVisualEvidenceParams(
            brand_id=brand_id,
            expected_workspace_version=1,
            source_url=source_url,
            observation="Unreviewed source.",
        ),
    )

    assert result.status == "error"
    assert result.error_code == "VBS_EVIDENCE_URL_REJECTED"


@pytest.mark.asyncio
async def test_evidence_access_and_stale_workspace_writes_fail_closed():
    owner = MockContext(user_id="owner", tenant_id="tenant-a")
    brand_id = await _brand_and_workspace(owner)

    first = await m.register_visual_evidence(
        owner,
        RegisterVisualEvidenceParams(
            brand_id=brand_id,
            expected_workspace_version=1,
            source_url="https://example.org/reference",
            observation="Unreviewed source.",
        ),
    )
    assert first.status == "success"

    stale = await m.register_visual_evidence(
        owner,
        RegisterVisualEvidenceParams(
            brand_id=brand_id,
            expected_workspace_version=1,
            source_url="https://example.org/second-reference",
            observation="This write uses an old workspace snapshot.",
        ),
    )
    assert stale.status == "error"
    assert stale.error_code == "VBS_STALE_WORKSPACE"

    other = MockContext(user_id="other", tenant_id="tenant-a")
    other.store = owner.store
    denied = await m.list_visual_evidence(other, ListVisualEvidenceParams(brand_id=brand_id))
    assert denied.status == "error"
    assert denied.error_code == "VBS_ACCESS_DENIED"

    audit = await m.list_visual_brand_audit_events(owner, m.ListVisualBrandAuditEventsParams(brand_id=brand_id))
    assert audit.status == "success"
    assert "evidence_registered" in {event.event_type for event in audit.data.items}
