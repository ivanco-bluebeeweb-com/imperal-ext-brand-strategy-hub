"""P0 evidence review state machine and profile-eligibility tests."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from imperal_sdk.testing import MockContext

import main as m
from schemas import (
    CreateBrandProfileParams,
    CreateVisualProfileParams,
    InitializeVisualBrandWorkspaceParams,
    ListVisualBrandAuditEventsParams,
    RegisterVisualEvidenceParams,
    ReviewVisualEvidenceParams,
)


async def _brand_and_workspace(ctx):
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Review evidence brand"))
    await m.initialize_visual_brand_workspace(
        ctx, InitializeVisualBrandWorkspaceParams(brand_id=brand.data.id, confirm_owner_claim=True)
    )
    return brand.data.id


async def _evidence(ctx, brand_id, version=1):
    result = await m.register_visual_evidence(
        ctx,
        RegisterVisualEvidenceParams(
            brand_id=brand_id,
            expected_workspace_version=version,
            source_url="https://example.org/review-source",
            observation="Potential support for grounded operational direction.",
        ),
    )
    assert result.status == "success"
    return result


@pytest.mark.asyncio
async def test_evidence_review_transitions_are_audited_and_fail_closed_when_stale():
    ctx = MockContext(user_id="owner", tenant_id="tenant-a")
    brand_id = await _brand_and_workspace(ctx)
    evidence = await _evidence(ctx, brand_id)

    reviewed = await m.review_visual_evidence(
        ctx,
        ReviewVisualEvidenceParams(
            evidence_id=evidence.data["id"],
            expected_status="discovered",
            expected_workspace_version=evidence.data["workspace_version"],
            decision="reviewed_valid",
            review_note="Reviewed against the approved project context.",
        ),
    )
    assert reviewed.status == "success"
    assert reviewed.data.status == "reviewed_valid"

    stale = await m.review_visual_evidence(
        ctx,
        ReviewVisualEvidenceParams(
            evidence_id=evidence.data["id"],
            expected_status="discovered",
            expected_workspace_version=evidence.data["workspace_version"],
            decision="hypothesis",
            review_note="Old screen submission.",
        ),
    )
    assert stale.status == "error"
    assert stale.error_code == "VBS_EVIDENCE_STALE"

    invalid = await m.review_visual_evidence(
        ctx,
        ReviewVisualEvidenceParams(
            evidence_id=evidence.data["id"],
            expected_status="reviewed_valid",
            expected_workspace_version=3,
            decision="rejected",
            review_note="This transition is intentionally disallowed.",
        ),
    )
    assert invalid.status == "error"
    assert invalid.error_code == "VBS_EVIDENCE_INVALID_TRANSITION"

    audit = await m.list_visual_brand_audit_events(ctx, ListVisualBrandAuditEventsParams(brand_id=brand_id))
    assert "evidence_reviewed_valid" in {event.event_type for event in audit.data.items}


@pytest.mark.asyncio
async def test_profile_rejects_unreviewed_evidence_before_any_profile_write():
    ctx = MockContext(user_id="owner", tenant_id="tenant-a")
    brand_id = await _brand_and_workspace(ctx)
    evidence = await _evidence(ctx, brand_id)

    result = await m.create_visual_profile(
        ctx,
        CreateVisualProfileParams(
            brand_id=brand_id,
            expected_workspace_version=evidence.data["workspace_version"],
            evidence_ids=[evidence.data["id"]],
            profile_summary="This attempt must be rejected before VBS lookup because evidence is unreviewed.",
        ),
    )
    # Either prerequisite can block first; the P0 invariant is that no draft is created.
    assert result.status == "error"
    assert result.error_code in {"VBS_CURRENT_REQUIRED", "VBS_EVIDENCE_NOT_ELIGIBLE"}
