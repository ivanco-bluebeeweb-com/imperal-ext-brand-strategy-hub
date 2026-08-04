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


class BrandProfileList(sdl.EntityList[BrandProfile]):
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
    Markdown for quick human reading."""
    brand_id: str = ""
    strengths: list[str] = []
    weaknesses: list[str] = []
    opportunities: list[str] = []
    threats: list[str] = []


class SWOTResultList(sdl.EntityList[SWOTResult]):
    pass


class GapAnalysisResult(sdl.Entity, sdl.Bodied):
    """One brand-vs-audience gap analysis: what a target segment needs that
    the brand's current positioning does not yet address, plus concrete
    'fill the gap' recommendations."""
    brand_id: str = ""
    segment_id: str = ""
    gaps: list[str] = []
    recommendations: list[str] = []


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


class UpdateBrandProfileParams(BaseModel):
    brand_id: str = Field(description="UUID of an existing brand profile — from list_brand_profiles, never invented")
    brand_name: str | None = Field(default=None, description="New brand name; omit to keep")
    mission: str | None = Field(default=None, description="New mission; omit to keep")
    vision: str | None = Field(default=None, description="New vision; omit to keep")
    value_proposition: str | None = Field(default=None, description="New value proposition; omit to keep")
    tone_of_voice: str | None = Field(default=None, description="New tone of voice; omit to keep")
    unique_selling_points: list[str] | None = Field(default=None, description="Replace USPs; omit to keep")
    industry: str | None = Field(default=None, description="New industry; omit to keep")


class ListBrandProfilesParams(BaseModel):
    limit: int = Field(20, description="Max items to return (1-100)")


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


class RunGapAnalysisParams(BaseModel):
    brand_id: str = Field(description="UUID of an existing brand profile — from list_brand_profiles, never invented")
    segment_id: str = Field(description="UUID of an existing target segment — from list_target_segments, never invented")


class ListGapAnalysesParams(BaseModel):
    brand_id: str = Field("", description="Optional brand filter. Empty = all.")
    limit: int = Field(20, description="Max items to return (1-100)")


class BuildContentStrategyHandoffParams(BaseModel):
    brand_id: str = Field(description="UUID of an existing brand profile — from list_brand_profiles, never invented")
    site_id: str = Field(description="Site id to use downstream, e.g. 'g4s.md' — matches Content Strategy Hub's site_id")
    domain: str = Field("", description="Domain for the site; defaults to site_id if omitted")
    target_languages: list[str] = Field(default_factory=list, description="Target languages for content, e.g. ['ru','ro']")
