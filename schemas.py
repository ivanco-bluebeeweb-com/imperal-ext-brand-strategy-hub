"""Pydantic params models + SDL entity contracts for Brand Strategy Hub.

All params models are module-scope (V17 federal invariant).
Entities/EntityLists follow the read-tool contract (V23): a single record
is an sdl.Entity subclass, a list result is sdl.EntityList[T] — never a
bare dict wrapper.
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from imperal_sdk import sdl

# ──────────────────────────────────────────────────────────────────────────
# Domain entities
# ──────────────────────────────────────────────────────────────────────────


class BrandProfile(sdl.Entity):
    """One brand under strategic analysis — the anchor every SWOT, segment,
    and gap-analysis result links back to via brand_id."""
    site_id: str = ""  # optional link to Content Strategy Hub's site_id
    brand_name: str = ""
    mission: str = ""
    vision: str = ""
    value_proposition: str = ""
    tone_of_voice: str = ""
    unique_selling_points: list[str] = []
    industry: str = ""
    content_topics: list[str] = []  # topics/categories THIS brand's content should cover -- distinct from unique_selling_points (differentiators, not topics). Feeds build_content_strategy_handoff.content_categories.


class BrandProfileList(sdl.EntityList[BrandProfile]):
    pass


class VisualBrandWorkspace(sdl.Entity):
    """Private ownership boundary and optimistic-concurrency counter for one brand."""
    brand_id: str = ""
    owner_id: str = ""
    tenant_id: str = ""
    version: int = 1
    status: str = "ready"


class VisualBrandSystem(sdl.Entity):
    """One versioned Visual Brand System draft or approved revision.

    This first P0 slice deliberately contains only non-personal, non-media
    fields. People, consent, licenses and generation gates remain blocked
    until their separate privacy and storage spikes are complete.
    """
    brand_id: str = ""
    revision: int = 1
    status: str = "draft"
    visual_intent: str = ""
    realism_level: str = ""
    core_rules: list[str] = []
    prohibited_patterns: list[str] = []
    change_note: str = ""
    created_by: str = ""
    tenant_id: str = ""
    supersedes_vbs_id: str = ""


class VisualBrandSystemList(sdl.EntityList[VisualBrandSystem]):
    pass


class AuditEvent(sdl.Entity):
    """Append-only audit record for a VBS action in this application."""
    brand_id: str = ""
    vbs_id: str = ""
    event_type: str = ""
    actor_id: str = ""
    tenant_id: str = ""
    details: str = ""


class AuditEventList(sdl.EntityList[AuditEvent]):
    pass


class CompetitorProfile(sdl.Entity):
    """One named competitor tracked against a brand."""
    brand_id: str = ""
    name: str = ""
    url: str = ""
    strengths: list[str] = []
    weaknesses: list[str] = []
    notes: str = ""


class CompetitorProfileList(sdl.EntityList[CompetitorProfile]):
    pass


class TargetSegment(sdl.Entity):
    """One audience segment a brand is trying to reach."""
    brand_id: str = ""
    segment_name: str = ""
    demographics: str = ""
    psychographics: str = ""
    pain_points: list[str] = []
    needs: list[str] = []
    preferred_channels: list[str] = []


class TargetSegmentList(sdl.EntityList[TargetSegment]):
    pass


class SWOTResult(sdl.Entity, sdl.Bodied):
    """One SWOT analysis snapshot for a brand, derived from its profile and
    tracked competitors. `body` (from sdl.Bodied) renders the full SWOT as
    Markdown for quick human reading.

    is_current marks the ONE live snapshot per brand -- running a new SWOT
    automatically supersedes the previous current one (sets its is_current
    to False and stamps superseded_at) rather than leaving two snapshots
    both looking equally authoritative."""
    brand_id: str = ""
    strengths: list[str] = []
    weaknesses: list[str] = []
    opportunities: list[str] = []
    threats: list[str] = []
    is_current: bool = True
    superseded_at: str = ""


class SWOTResultList(sdl.EntityList[SWOTResult]):
    pass


class GapAnalysisResult(sdl.Entity, sdl.Bodied):
    """One brand-vs-audience gap analysis: what a target segment needs that
    the brand's current positioning does not yet address, plus concrete
    'fill the gap' recommendations.

    is_current marks the ONE live analysis per (brand_id, segment_id) pair --
    re-running for the same segment supersedes the previous current result
    instead of leaving two, so a reader never has to guess which is fresh."""
    brand_id: str = ""
    segment_id: str = ""
    gaps: list[str] = []
    recommendations: list[str] = []
    is_current: bool = True
    superseded_at: str = ""


class GapAnalysisResultList(sdl.EntityList[GapAnalysisResult]):
    pass


class BrandContentHandoff(sdl.Entity, sdl.Bodied):
    """Reshapes a brand profile into the exact fields Content Strategy Hub's
    create_site_profile/update expects, so brand strategy work does not have
    to be manually re-typed into the content-planning layer downstream.
    There is no direct extension-to-extension call on this platform — Webbee
    relays this payload into Content Strategy Hub's own tool in the same
    chat turn."""
    brand_id: str = ""
    site_id: str = ""  # -> content-strategy-app.create_site_profile(site_id=...)
    domain: str = ""  # -> create_site_profile(domain=...)
    brand_name: str = ""  # -> create_site_profile(brand_name=...)
    business_description: str = ""  # -> create_site_profile(business_description=...)
    content_categories: list[str] = []  # -> create_site_profile(content_categories=...)
    cta_default: str = ""  # -> create_site_profile(cta_default=...)
    target_languages: list[str] = []  # -> create_site_profile(target_languages=...)


# ──────────────────────────────────────────────────────────────────────────
# @chat.function params models
# ──────────────────────────────────────────────────────────────────────────

class CreateBrandProfileParams(BaseModel):
    brand_name: str = Field(min_length=1, description="Brand/company name")
    site_id: str = Field("", description="Optional link to a Content Strategy Hub site_id, e.g. 'g4s.md'")
    mission: str = Field("", description="One or two sentences on why the brand exists")
    vision: str = Field("", description="One or two sentences on where the brand wants to be")
    value_proposition: str = Field("", description="The core promise made to customers")
    tone_of_voice: str = Field("", description="How the brand sounds, e.g. 'confident, warm, no jargon'")
    unique_selling_points: list[str] = Field(default_factory=list, description="What makes this brand different, one point per item")
    industry: str = Field("", description="Industry/category, e.g. 'private security services'")
    content_topics: list[str] = Field(default_factory=list, description="Topics/categories this brand's content should cover, e.g. ['ventilation systems', 'heat recovery', 'installation guides'] -- distinct from unique_selling_points. Used by build_content_strategy_handoff to populate content_categories.")


class UpdateBrandProfileParams(BaseModel):
    brand_id: str = Field(description="UUID of an existing brand profile — from list_brand_profiles, never invented")
    brand_name: str | None = Field(default=None, description="New brand name; omit to keep")
    mission: str | None = Field(default=None, description="New mission; omit to keep")
    vision: str | None = Field(default=None, description="New vision; omit to keep")
    value_proposition: str | None = Field(default=None, description="New value proposition; omit to keep")
    tone_of_voice: str | None = Field(default=None, description="New tone of voice; omit to keep")
    unique_selling_points: list[str] | None = Field(default=None, description="Replace USPs; omit to keep")
    industry: str | None = Field(default=None, description="New industry; omit to keep")
    content_topics: list[str] | None = Field(default=None, description="Replace content topics/categories; omit to keep")


class ListBrandProfilesParams(BaseModel):
    limit: int = Field(20, description="Max items to return (1-100)")


# ──────────────────────────────────────────────────────────────────────────
# Visual Brand System — P0 non-personal vertical slice
# ──────────────────────────────────────────────────────────────────────────

class InitializeVisualBrandWorkspaceParams(BaseModel):
    brand_id: str = Field(description="UUID of an existing brand profile — never invented")
    confirm_owner_claim: bool = Field(
        False,
        description=(
            "Must be explicitly true. In this P0 spike, bind an unscoped legacy "
            "brand to the current tenant and workspace owner."
        ),
    )


class CreateVisualBrandSystemParams(BaseModel):
    brand_id: str = Field(description="UUID of an existing brand profile — never invented")
    expected_workspace_version: int = Field(
        ge=1,
        description="Workspace version currently shown in the UI; blocks stale writes in this P0 flow",
    )
    visual_intent: str = Field(min_length=1, description="What the visual system should make the audience feel or understand")
    realism_level: str = Field(
        "", description="Declared visual mode, e.g. 'grounded realism' or 'stylised illustration'"
    )
    core_rules: list[str] = Field(default_factory=list, description="Non-negotiable visual rules, one per item")
    prohibited_patterns: list[str] = Field(default_factory=list, description="Visual patterns that must not be used, one per item")
    change_note: str = Field("", description="Why this initial VBS draft is being created")


class ListVisualBrandSystemsParams(BaseModel):
    brand_id: str = Field(description="UUID of an existing brand profile — never invented")
    include_superseded: bool = Field(False, description="Include superseded and archived VBS revisions")


class ActivateVisualBrandSystemParams(BaseModel):
    vbs_id: str = Field(description="UUID of a VBS draft or in-review revision — never invented")
    expected_revision: int = Field(ge=1, description="Revision currently shown to the reviewer; blocks stale activation")
    approval_note: str = Field("", description="Reason for approving this VBS revision")


class ListVisualBrandAuditEventsParams(BaseModel):
    brand_id: str = Field(description="UUID of an existing brand profile — never invented")
    limit: int = Field(50, description="Max audit events to return (1-100)")


class AddCompetitorParams(BaseModel):
    brand_id: str = Field(description="UUID of an existing brand profile — from list_brand_profiles, never invented")
    name: str = Field(min_length=1, description="Competitor name")
    url: str = Field("", description="Competitor website")
    strengths: list[str] = Field(default_factory=list, description="What the competitor does well")
    weaknesses: list[str] = Field(default_factory=list, description="Where the competitor falls short")
    notes: str = Field("", description="Freeform observations")


class ListCompetitorsParams(BaseModel):
    brand_id: str = Field("", description="Optional brand filter. Empty = all.")
    limit: int = Field(20, description="Max items to return (1-100)")


class CreateTargetSegmentParams(BaseModel):
    brand_id: str = Field(description="UUID of an existing brand profile — from list_brand_profiles, never invented")
    segment_name: str = Field(min_length=1, description="Segment label, e.g. 'SMB office managers'")
    demographics: str = Field("", description="Age, role, company size, location, etc.")
    psychographics: str = Field("", description="Values, motivations, attitudes")
    pain_points: list[str] = Field(default_factory=list, description="Problems this segment currently has")
    needs: list[str] = Field(default_factory=list, description="What this segment is looking for")
    preferred_channels: list[str] = Field(default_factory=list, description="Where this segment can be reached, e.g. 'LinkedIn', 'local search'")


class ListTargetSegmentsParams(BaseModel):
    brand_id: str = Field("", description="Optional brand filter. Empty = all.")
    limit: int = Field(20, description="Max items to return (1-100)")


class RunSWOTAnalysisParams(BaseModel):
    brand_id: str = Field(description="UUID of an existing brand profile — from list_brand_profiles, never invented")


class ListSWOTResultsParams(BaseModel):
    brand_id: str = Field("", description="Optional brand filter. Empty = all.")
    limit: int = Field(20, description="Max items to return (1-100)")
    include_superseded: bool = Field(
        False,
        description=(
            "False (default) returns only the CURRENT snapshot per brand -- "
            "what a reader should actually act on. Set true to also see "
            "superseded (outdated) SWOT history."
        ),
    )


class RunGapAnalysisParams(BaseModel):
    brand_id: str = Field(description="UUID of an existing brand profile — from list_brand_profiles, never invented")
    segment_id: str = Field(description="UUID of an existing target segment — from list_target_segments, never invented")


class ListGapAnalysesParams(BaseModel):
    brand_id: str = Field("", description="Optional brand filter. Empty = all.")
    limit: int = Field(20, description="Max items to return (1-100)")
    include_superseded: bool = Field(
        False,
        description=(
            "False (default) returns only the CURRENT result per (brand, "
            "segment) pair. Set true to also see superseded (outdated) "
            "gap-analysis history."
        ),
    )


class BuildContentStrategyHandoffParams(BaseModel):
    brand_id: str = Field(description="UUID of an existing brand profile — from list_brand_profiles, never invented")
    site_id: str = Field(description="Site id to use downstream, e.g. 'g4s.md' — matches Content Strategy Hub's site_id")
    domain: str = Field("", description="Domain for the site; defaults to site_id if omitted")
    target_languages: list[str] = Field(default_factory=list, description="Target languages for content, e.g. ['ru','ro']")


# ──────────────────────────────────────────────────────────────────────────
# Deletion / archival — brand profiles are the anchor for every other
# collection, so removing one always cascades to what it anchors rather
# than leaving orphaned competitors/segments/SWOTs/gap analyses behind.
# ──────────────────────────────────────────────────────────────────────────

class DeleteResult(sdl.Entity):
    """Outcome of a single-record delete."""
    deleted: bool = False


class DeleteBrandProfileParams(BaseModel):
    brand_id: str = Field(description="UUID of an existing brand profile — from list_brand_profiles, never invented")
    confirm_cascade: bool = Field(
        False,
        description=(
            "Must be explicitly true. Deleting a brand profile cascades to ALL "
            "of its competitors, target segments, SWOT snapshots, and gap "
            "analyses — irreversible."
        ),
    )


class DeleteCompetitorParams(BaseModel):
    competitor_id: str = Field(description="UUID of an existing competitor — from list_brand_competitors, never invented")


class DeleteTargetSegmentParams(BaseModel):
    segment_id: str = Field(description="UUID of an existing target segment — from list_target_segments, never invented")


class ArchiveSWOTResultParams(BaseModel):
    swot_id: str = Field(description="UUID of an existing SWOT snapshot — from list_swot_results, never invented")


class ArchiveGapAnalysisParams(BaseModel):
    gap_analysis_id: str = Field(description="UUID of an existing gap analysis — from list_gap_analyses, never invented")


class PurgeBrandStrategyDataParams(BaseModel):
    confirm_wipe: bool = Field(
        False,
        description=(
            "Must be explicitly true to run the purge. Safety flag so this can "
            "never fire by accident from a misread instruction."
        ),
    )


class PurgeResult(sdl.Entity):
    """Outcome of a full brand-strategy data wipe — counts removed per
    collection. Brand profiles themselves are never touched by this."""
    competitors_removed: int = 0
    segments_removed: int = 0
    swot_results_removed: int = 0
    gap_analyses_removed: int = 0
    kept_brand_ids: list[str] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────
# Cross-app site discovery (Quick Add source)
# ──────────────────────────────────────────────────────────────────────────


class ConnectedSite(sdl.Entity):
    """One site read from a site-provider extension (WordPress Hub today,
    more providers later) — the raw material behind the Quick Add list."""
    site_id: str = ""
    url: str = ""
    status: str = ""
    provider: str = ""
    already_tracked: bool = False


class ConnectedSiteList(sdl.EntityList[ConnectedSite]):
    pass


class ListConnectedSitesParams(BaseModel):
    limit: int = Field(50, description="Max items to return (1-100)")
