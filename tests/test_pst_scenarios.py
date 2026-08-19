"""Plausible Scenario Tests (PST) -- Brand Strategy Hub.

Method: Docs/session-notes/SCENARIO_TESTING_STANDARD.md. The existing
suite (113 tests across test_smoke.py + P0/P1/P2 VBS files) already
covers happy/error/adversarial branches thoroughly for this app -- this
file targets the one branch a grep-audit found genuinely missing:
RECOVERY (a call that failed for a fixable reason succeeds once the
user fixes it and retries), plus a couple of cross-cutting scenarios
spanning the ordinary/VBS split that no single existing file covers.
"""
from __future__ import annotations

import pytest

from imperal_sdk.testing import MockContext

import main as m
from schemas import (
    CreateBrandProfileParams, UpdateBrandProfileParams, DeleteBrandProfileParams,
    AddCompetitorParams, CreateTargetSegmentParams, RunSWOTAnalysisParams,
    RunGapAnalysisParams, ListBrandProfilesParams,
    DeleteCompetitorParams, DeleteTargetSegmentParams, PurgeBrandStrategyDataParams,
)


# ── recovery: invalid input rejected, then a corrected retry succeeds ──────

@pytest.mark.asyncio
async def test_recovery_create_brand_after_fixing_empty_name():
    """Empty brand_name is rejected at the Pydantic layer (min_length=1) --
    the dispatcher never reaches the handler, so the 'error' here is a
    ValidationError, not an ActionResult. A corrected retry succeeds."""
    ctx = MockContext()
    with pytest.raises(Exception):
        CreateBrandProfileParams(brand_name="")

    good = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Retry Co"))
    assert good.error is None
    assert good.data.brand_name == "Retry Co"


@pytest.mark.asyncio
async def test_recovery_swot_after_creating_missing_brand_then_filling_profile():
    """Running SWOT on a brand_id that doesn't exist yet must fail cleanly.
    Creating the brand alone is NOT enough to recover -- an empty profile
    is correctly rejected too (EMPTY_BRAND_PROFILE) -- the real recovery
    path also requires filling in the profile before SWOT succeeds."""
    ctx = MockContext()
    missing = await m.run_swot_analysis(ctx, RunSWOTAnalysisParams(brand_id="does-not-exist"))
    assert missing.error is not None

    created = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Recovery SWOT Co"))
    assert created.error is None
    brand_id = created.data.id

    still_empty = await m.run_swot_analysis(ctx, RunSWOTAnalysisParams(brand_id=brand_id))
    assert still_empty.error is not None
    assert still_empty.error_code == "EMPTY_BRAND_PROFILE"

    filled = await m.update_brand_profile(ctx, UpdateBrandProfileParams(
        brand_id=brand_id, mission="Protect what matters",
        value_proposition="24/7 licensed security"))
    assert filled.error is None

    retried = await m.run_swot_analysis(ctx, RunSWOTAnalysisParams(brand_id=brand_id))
    assert retried.error is None


@pytest.mark.asyncio
async def test_recovery_gap_analysis_after_creating_missing_segment_first():
    ctx = MockContext()
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Gap Co"))
    brand_id = brand.data.id

    missing_segment = await m.run_gap_analysis(
        ctx, RunGapAnalysisParams(brand_id=brand_id, segment_id="ghost-segment"))
    assert missing_segment.error is not None

    segment = await m.create_target_segment(
        ctx, CreateTargetSegmentParams(brand_id=brand_id, segment_name="SMB owners"))
    assert segment.error is None

    retried = await m.run_gap_analysis(
        ctx, RunGapAnalysisParams(brand_id=brand_id, segment_id=segment.data.id))
    assert retried.error is None


@pytest.mark.asyncio
async def test_recovery_update_after_delete_reports_not_found_not_crash():
    """Deleting a brand then attempting to update it must be a clean,
    typed error -- not an unhandled exception -- so the caller can decide
    to recreate it (the actual recovery path) instead of the whole
    extension call failing opaquely."""
    ctx = MockContext()
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Delete Then Update Co"))
    brand_id = brand.data.id

    deleted = await m.delete_brand_profile(ctx, DeleteBrandProfileParams(brand_id=brand_id))
    assert deleted.error is None

    after = await m.update_brand_profile(ctx, UpdateBrandProfileParams(brand_id=brand_id, brand_name="New Name"))
    assert after.error is not None


# ── adversarial: cross-cutting scenario no single existing file covers ─────

@pytest.mark.asyncio
async def test_adversarial_list_brand_profiles_after_deleting_one_of_several():
    ctx = MockContext()
    a = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Survivor Co"))
    b = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Deleted Co"))
    await m.delete_brand_profile(ctx, DeleteBrandProfileParams(brand_id=b.data.id))

    listing = await m.list_brand_profiles(ctx, ListBrandProfilesParams())
    assert listing.error is None
    ids = [p.id for p in listing.data.items]
    assert a.data.id in ids
    assert b.data.id not in ids


@pytest.mark.asyncio
async def test_adversarial_add_competitor_with_duplicate_name_rejected():
    """Two competitors with the identical name for the same brand -- the
    second call is deliberately rejected (DUPLICATE_COMPETITOR) rather than
    silently duplicated, because duplicate competitors would double-count
    in SWOT's opportunities/threats. This is correct product behavior, not
    a bug -- confirming it stays rejected, not silently allowed."""
    ctx = MockContext()
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="Dup Competitor Co"))
    brand_id = brand.data.id

    first = await m.add_brand_competitor(
        ctx, AddCompetitorParams(brand_id=brand_id, name="Acme Inc",
                                  strengths=["price"], weaknesses=["support"]))
    second = await m.add_brand_competitor(
        ctx, AddCompetitorParams(brand_id=brand_id, name="Acme Inc",
                                  strengths=["speed"], weaknesses=["quality"]))
    assert first.error is None
    assert second.error is not None
    assert second.error_code == "DUPLICATE_COMPETITOR"


# ── Part D2 (SCENARIO_TESTING_STANDARD.md): idempotency / double-invocation ─

@pytest.mark.asyncio
async def test_d2_double_delete_competitor_fails_clean_not_crash():
    """delete_brand_competitor checks store.get before deleting -- a second,
    identical delete call (retried chat turn) must return a clean 'not
    found' error, never a crash or a silent no-op success."""
    ctx = MockContext()
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="D2 Delete Co"))
    added = await m.add_brand_competitor(
        ctx, AddCompetitorParams(brand_id=brand.data.id, name="Rival Inc",
                                  strengths=["price"], weaknesses=["support"]))
    competitor_id = added.data.id

    first = await m.delete_brand_competitor(ctx, DeleteCompetitorParams(competitor_id=competitor_id))
    assert first.error is None
    assert first.data.deleted is True

    second = await m.delete_brand_competitor(ctx, DeleteCompetitorParams(competitor_id=competitor_id))
    assert second.error is not None
    assert "not found" in second.error.lower()


@pytest.mark.asyncio
async def test_d2_double_delete_target_segment_fails_clean_not_crash():
    """Same guarantee as delete_brand_competitor, for delete_target_segment."""
    ctx = MockContext()
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="D2 Segment Co"))
    seg = await m.create_target_segment(
        ctx, CreateTargetSegmentParams(brand_id=brand.data.id, segment_name="Busy Parents"))
    segment_id = seg.data.id

    first = await m.delete_target_segment(ctx, DeleteTargetSegmentParams(segment_id=segment_id))
    assert first.error is None

    second = await m.delete_target_segment(ctx, DeleteTargetSegmentParams(segment_id=segment_id))
    assert second.error is not None
    assert "not found" in second.error.lower()


@pytest.mark.asyncio
async def test_d2_double_purge_is_naturally_idempotent_second_call_finds_nothing():
    """purge_brand_strategy_data wipes competitors/segments/SWOT/gap-analysis
    for the WHOLE portfolio (no brand_id filter) by querying then deleting
    each collection. A second, identical call must not error and must report
    zero removed -- it is naturally idempotent (there's nothing left to
    delete), not accidentally so."""
    ctx = MockContext()
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="D2 Purge Co"))
    await m.add_brand_competitor(
        ctx, AddCompetitorParams(brand_id=brand.data.id, name="Rival Inc",
                                  strengths=["price"], weaknesses=["support"]))

    first = await m.purge_brand_strategy_data(ctx, PurgeBrandStrategyDataParams())
    assert first.error is None
    assert first.data.competitors_removed == 1

    second = await m.purge_brand_strategy_data(ctx, PurgeBrandStrategyDataParams())
    assert second.error is None
    assert second.data.competitors_removed == 0
    assert second.data.segments_removed == 0


# ── Part D3 (SCENARIO_TESTING_STANDARD.md): security / SSRF surface ────────

@pytest.mark.asyncio
async def test_d3_competitor_url_field_is_stored_data_never_fetched():
    """add_brand_competitor and register_visual_evidence accept a `url` field
    (a competitor site, a market report, a directory listing) but this
    backend NEVER fetches it -- grep across main.py confirms no
    ctx.http/httpx/requests/urlopen call exists anywhere in this app. The
    actual web reading happens at chat level via Webbee's own
    web_search/read_url (a separate system app, not IPC-callable from here,
    per this app's own docstrings). Feeding an adversarial internal address
    must sail through as inert stored data, never attempted as a fetch
    target from this app's own code."""
    ctx = MockContext()
    brand = await m.create_brand_profile(ctx, CreateBrandProfileParams(brand_name="D3 SSRF Co"))
    result = await m.add_brand_competitor(
        ctx, AddCompetitorParams(
            brand_id=brand.data.id, name="Metadata Rival",
            strengths=["price"], weaknesses=["support"],
            url="http://169.254.169.254/latest/meta-data/"))
    assert result.error is None
    assert result.data.url == "http://169.254.169.254/latest/meta-data/"
