"""Brand Strategy Hub — decides who the brand IS, who it's for, and where
the gaps are: brand profile, competitor tracking, target segments, SWOT
analysis, and brand-vs-audience gap analysis with 'fill the gap'
recommendations. Feeds the rest of the marketing pipeline (Content
Strategy Hub -> Article Writer -> Media Studio Hub -> WordPress Hub) a
structured brand context via build_content_strategy_handoff.

Boundaries:
- does NOT plan individual articles/opportunities (Content Strategy Hub's job)
- does NOT write copy (Article Writer's job)
- does NOT generate images (Media Studio Hub's job)
- does NOT publish (WordPress Hub's job)

Everything that registers against `ext`/`chat` lives directly in this file.
schemas.py and converters.py are pure leaf modules imported one-way from
here -- nothing imports back from main.py, which is what the platform's
deploy loader requires (it loads main.py by path, not as a package, so any
handler module trying to import `chat`/`ext` back out of main.py ends up
talking to a second, empty copy of this module).
"""
from __future__ import annotations

from imperal_sdk import ActionResult, Extension, ChatExtension, ui

from schemas import (
    AddCompetitorParams, BuildContentStrategyHandoffParams,
    CreateBrandProfileParams, CreateTargetSegmentParams,
    ListBrandProfilesParams, ListCompetitorsParams, ListGapAnalysesParams,
    ListSWOTResultsParams, ListTargetSegmentsParams, RunGapAnalysisParams,
    RunSWOTAnalysisParams, UpdateBrandProfileParams,
    BrandContentHandoff,
    BrandProfile, BrandProfileList,
    CompetitorProfile, CompetitorProfileList,
    GapAnalysisResult, GapAnalysisResultList,
    SWOTResult, SWOTResultList,
    TargetSegment, TargetSegmentList,
)
from converters import (
    build_gap_analysis, build_swot,
    to_brand_profile as _to_brand_profile,
    to_competitor_profile as _to_competitor_profile,
    to_content_handoff as _to_content_handoff,
    to_gap_analysis_result as _to_gap_analysis_result,
    to_swot_result as _to_swot_result,
    to_target_segment as _to_target_segment,
)

ext = Extension(
    "brand-strategy-hub",
    version="1.0.0",
    display_name="Brand Strategy Hub",
    description=(
        "Defines who your brand is and who it's for: brand profile (mission, "
        "value proposition, USPs), tracked competitors, target audience "
        "segments, SWOT analysis, and brand-vs-audience gap analysis with "
        "concrete recommendations to fill the gap. Hands a structured brand "
        "context downstream to Content Strategy Hub so the rest of the "
        "content pipeline is grounded in real positioning, not guesswork."
    ),
    icon="icon.svg",
    actions_explicit=True,
    capabilities=["brand-strategy:read", "brand-strategy:write"],
)

chat = ChatExtension(
    ext, tool_name="brand-strategy-hub",
    description="Brand profile, competitors, target segments, SWOT and brand-audience gap analysis",
)


@ext.health_check
async def health_check(ctx) -> dict:
    """Liveness probe for the extension."""
    return {"status": "ok"}


# ──────────────────────────────────────────────────────────────────────────
# Brand profile
# ──────────────────────────────────────────────────────────────────────────

@chat.function(
    "create_brand_profile",
    description=(
        "Create a new brand profile — mission, vision, value proposition, "
        "tone of voice, and unique selling points. The anchor for SWOT, "
        "competitor tracking, and target segments for this brand."
    ),
    action_type="write",
    chain_callable=True,
    effects=["create:brand_profile"],
    event="created",
    data_model=BrandProfile,
)
async def create_brand_profile(ctx, params: CreateBrandProfileParams) -> ActionResult:
    """Create one brand profile."""
    doc = await ctx.store.create(
        "brand_profiles",
        {
            "site_id": params.site_id,
            "brand_name": params.brand_name,
            "mission": params.mission,
            "vision": params.vision,
            "value_proposition": params.value_proposition,
            "tone_of_voice": params.tone_of_voice,
            "unique_selling_points": params.unique_selling_points,
            "industry": params.industry,
        },
    )
    return ActionResult.success(
        _to_brand_profile(doc),
        summary=f"Brand profile created: {params.brand_name}",
    )


@chat.function(
    "update_brand_profile",
    description="Update selected fields of an existing brand profile. Only given fields change.",
    action_type="write",
    chain_callable=True,
    effects=["update:brand_profile"],
    event="updated",
    id_projection="brand_id",
    data_model=BrandProfile,
)
async def update_brand_profile(ctx, params: UpdateBrandProfileParams) -> ActionResult:
    """Patch an existing brand profile with only the given fields."""
    doc = await ctx.store.get("brand_profiles", params.brand_id)
    if not doc:
        return ActionResult.error(f"Brand profile '{params.brand_id}' not found.", retryable=False)

    updates = {}
    for field in ("brand_name", "mission", "vision", "value_proposition", "tone_of_voice", "industry"):
        value = getattr(params, field)
        if value is not None:
            updates[field] = value
    if params.unique_selling_points is not None:
        updates["unique_selling_points"] = params.unique_selling_points

    if not updates:
        return ActionResult.error("No fields given to update.", retryable=False)

    updated = await ctx.store.update("brand_profiles", params.brand_id, updates)
    return ActionResult.success(_to_brand_profile(updated), summary="Brand profile updated.")


@chat.function(
    "list_brand_profiles",
    description="List brand profiles.",
    action_type="read",
    data_model=BrandProfileList,
)
async def list_brand_profiles(ctx, params: ListBrandProfilesParams) -> ActionResult:
    """List all brand profiles."""
    page = await ctx.store.query("brand_profiles", order_by="-created_at", limit=params.limit)
    items = [_to_brand_profile(d) for d in page.data]
    return ActionResult.success(BrandProfileList(items=items, total=len(items)), summary=f"{len(items)} brand profile(s).")


# ──────────────────────────────────────────────────────────────────────────
# Competitors
# ──────────────────────────────────────────────────────────────────────────

@chat.function(
    "add_competitor_profile",
    description="Track a named competitor against a brand, with observed strengths and weaknesses.",
    action_type="write",
    chain_callable=True,
    effects=["create:competitor_profile"],
    event="created",
    data_model=CompetitorProfile,
)
async def add_competitor_profile(ctx, params: AddCompetitorParams) -> ActionResult:
    """Add one competitor profile linked to a brand."""
    brand_doc = await ctx.store.get("brand_profiles", params.brand_id)
    if not brand_doc:
        return ActionResult.error(f"Brand profile '{params.brand_id}' not found.", retryable=False)

    doc = await ctx.store.create(
        "competitor_profiles",
        {
            "brand_id": params.brand_id,
            "name": params.name,
            "url": params.url,
            "strengths": params.strengths,
            "weaknesses": params.weaknesses,
            "notes": params.notes,
        },
    )
    return ActionResult.success(_to_competitor_profile(doc), summary=f"Competitor added: {params.name}")


@chat.function(
    "list_competitor_profiles",
    description="List tracked competitors, optionally filtered by brand.",
    action_type="read",
    data_model=CompetitorProfileList,
)
async def list_competitor_profiles(ctx, params: ListCompetitorsParams) -> ActionResult:
    """List competitor profiles, optionally filtered by brand."""
    page = await ctx.store.query("competitor_profiles", order_by="-created_at", limit=500)
    items = list(page.data)
    if params.brand_id:
        items = [d for d in items if d.data.get("brand_id") == params.brand_id]
    items = items[: params.limit]
    entities = [_to_competitor_profile(d) for d in items]
    return ActionResult.success(CompetitorProfileList(items=entities, total=len(entities)), summary=f"{len(entities)} competitor(s).")


# ──────────────────────────────────────────────────────────────────────────
# Target segments
# ──────────────────────────────────────────────────────────────────────────

@chat.function(
    "create_target_segment",
    description="Define one target audience segment for a brand: demographics, psychographics, pain points, needs, preferred channels.",
    action_type="write",
    chain_callable=True,
    effects=["create:target_segment"],
    event="created",
    data_model=TargetSegment,
)
async def create_target_segment(ctx, params: CreateTargetSegmentParams) -> ActionResult:
    """Create one target segment linked to a brand."""
    brand_doc = await ctx.store.get("brand_profiles", params.brand_id)
    if not brand_doc:
        return ActionResult.error(f"Brand profile '{params.brand_id}' not found.", retryable=False)

    doc = await ctx.store.create(
        "target_segments",
        {
            "brand_id": params.brand_id,
            "segment_name": params.segment_name,
            "demographics": params.demographics,
            "psychographics": params.psychographics,
            "pain_points": params.pain_points,
            "needs": params.needs,
            "preferred_channels": params.preferred_channels,
        },
    )
    return ActionResult.success(_to_target_segment(doc), summary=f"Target segment created: {params.segment_name}")


@chat.function(
    "list_target_segments",
    description="List target audience segments, optionally filtered by brand.",
    action_type="read",
    data_model=TargetSegmentList,
)
async def list_target_segments(ctx, params: ListTargetSegmentsParams) -> ActionResult:
    """List target segments, optionally filtered by brand."""
    page = await ctx.store.query("target_segments", order_by="-created_at", limit=500)
    items = list(page.data)
    if params.brand_id:
        items = [d for d in items if d.data.get("brand_id") == params.brand_id]
    items = items[: params.limit]
    entities = [_to_target_segment(d) for d in items]
    return ActionResult.success(TargetSegmentList(items=entities, total=len(entities)), summary=f"{len(entities)} target segment(s).")


# ──────────────────────────────────────────────────────────────────────────
# SWOT analysis
# ──────────────────────────────────────────────────────────────────────────

@chat.function(
    "run_swot_analysis",
    description=(
        "Run a SWOT analysis for a brand: strengths/weaknesses derived from "
        "its own profile, opportunities/threats derived from tracked "
        "competitors' weaknesses/strengths. Add competitors first via "
        "add_competitor_profile for a sharper result."
    ),
    action_type="write",
    chain_callable=True,
    effects=["create:swot_result"],
    event="created",
    data_model=SWOTResult,
)
async def run_swot_analysis(ctx, params: RunSWOTAnalysisParams) -> ActionResult:
    """Derive and store a SWOT snapshot for a brand."""
    brand_doc = await ctx.store.get("brand_profiles", params.brand_id)
    if not brand_doc:
        return ActionResult.error(f"Brand profile '{params.brand_id}' not found.", retryable=False)

    comp_page = await ctx.store.query("competitor_profiles", where={"brand_id": params.brand_id}, limit=500)
    competitors = [d.data for d in comp_page.data]

    strengths, weaknesses, opportunities, threats = build_swot(brand_doc.data, competitors)

    doc = await ctx.store.create(
        "swot_results",
        {
            "brand_id": params.brand_id,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "opportunities": opportunities,
            "threats": threats,
        },
    )
    return ActionResult.success(_to_swot_result(doc), summary=f"SWOT analysis run for brand {params.brand_id}.")


@chat.function(
    "list_swot_results",
    description="List past SWOT analysis snapshots, optionally filtered by brand.",
    action_type="read",
    data_model=SWOTResultList,
)
async def list_swot_results(ctx, params: ListSWOTResultsParams) -> ActionResult:
    """List SWOT results, optionally filtered by brand."""
    page = await ctx.store.query("swot_results", order_by="-created_at", limit=500)
    items = list(page.data)
    if params.brand_id:
        items = [d for d in items if d.data.get("brand_id") == params.brand_id]
    items = items[: params.limit]
    entities = [_to_swot_result(d) for d in items]
    return ActionResult.success(SWOTResultList(items=entities, total=len(entities)), summary=f"{len(entities)} SWOT result(s).")


# ──────────────────────────────────────────────────────────────────────────
# Brand-vs-audience gap analysis
# ──────────────────────────────────────────────────────────────────────────

@chat.function(
    "run_gap_analysis",
    description=(
        "Run a gap analysis between a brand's current positioning and one "
        "target segment's needs/pain points -- what the segment needs that "
        "the brand doesn't yet address, plus concrete recommendations to "
        "fill the gap."
    ),
    action_type="write",
    chain_callable=True,
    effects=["create:gap_analysis_result"],
    event="created",
    data_model=GapAnalysisResult,
)
async def run_gap_analysis(ctx, params: RunGapAnalysisParams) -> ActionResult:
    """Derive and store a brand-vs-audience gap analysis."""
    brand_doc = await ctx.store.get("brand_profiles", params.brand_id)
    if not brand_doc:
        return ActionResult.error(f"Brand profile '{params.brand_id}' not found.", retryable=False)
    segment_doc = await ctx.store.get("target_segments", params.segment_id)
    if not segment_doc:
        return ActionResult.error(f"Target segment '{params.segment_id}' not found.", retryable=False)

    gaps, recommendations = build_gap_analysis(brand_doc.data, segment_doc.data)

    doc = await ctx.store.create(
        "gap_analysis_results",
        {
            "brand_id": params.brand_id,
            "segment_id": params.segment_id,
            "gaps": gaps,
            "recommendations": recommendations,
        },
    )
    return ActionResult.success(_to_gap_analysis_result(doc), summary="Gap analysis run.")


@chat.function(
    "list_gap_analyses",
    description="List past brand-vs-audience gap analysis results, optionally filtered by brand.",
    action_type="read",
    data_model=GapAnalysisResultList,
)
async def list_gap_analyses(ctx, params: ListGapAnalysesParams) -> ActionResult:
    """List gap analysis results, optionally filtered by brand."""
    page = await ctx.store.query("gap_analysis_results", order_by="-created_at", limit=500)
    items = list(page.data)
    if params.brand_id:
        items = [d for d in items if d.data.get("brand_id") == params.brand_id]
    items = items[: params.limit]
    entities = [_to_gap_analysis_result(d) for d in items]
    return ActionResult.success(GapAnalysisResultList(items=entities, total=len(entities)), summary=f"{len(entities)} gap analysis result(s).")


# ──────────────────────────────────────────────────────────────────────────
# Pipeline handoff — Brand Strategy Hub -> Content Strategy Hub
# ──────────────────────────────────────────────────────────────────────────

@chat.function(
    "build_content_strategy_handoff",
    description=(
        "Reshape a brand profile into the exact fields Content Strategy "
        "Hub's create_site_profile expects, so the rest of the pipeline "
        "(Content Strategy Hub -> Article Writer -> Media Studio Hub -> "
        "WordPress Hub) starts from real brand positioning. There is no "
        "cross-extension IPC on this platform -- Webbee relays this payload "
        "into Content Strategy Hub's own create_site_profile in the same "
        "chat turn."
    ),
    action_type="read",
    data_model=BrandContentHandoff,
)
async def build_content_strategy_handoff(ctx, params: BuildContentStrategyHandoffParams) -> ActionResult:
    """Assemble a brand profile into Content Strategy Hub's create_site_profile shape."""
    brand_doc = await ctx.store.get("brand_profiles", params.brand_id)
    if not brand_doc:
        return ActionResult.error(f"Brand profile '{params.brand_id}' not found.", retryable=False)

    handoff = _to_content_handoff(
        brand_doc.data, params.brand_id, params.site_id, params.domain, params.target_languages
    )
    return ActionResult.success(handoff, summary=f"Content strategy handoff ready for site '{params.site_id}'.")


# ──────────────────────────────────────────────────────────────────────────
# Panels
# ──────────────────────────────────────────────────────────────────────────

@ext.panel(
    "brands",
    slot="left",
    title="Brands",
    icon="🎯",
    default_width=280,
    min_width=220,
    max_width=420,
)
async def brands_panel(ctx, **kwargs) -> object:
    """Sidebar list of tracked brand profiles -> opens the detail overlay."""
    page = await ctx.store.query("brand_profiles", order_by="-created_at", limit=200)
    docs = list(page.data)

    if not docs:
        return ui.Stack(
            direction="v",
            gap=3,
            children=[
                ui.Empty(
                    message="No brands yet — create one from chat to start a SWOT / gap analysis.",
                    icon="🎯",
                ),
            ],
        )

    items = []
    for d in docs:
        data = d.data
        items.append(
            ui.ListItem(
                id=d.id,
                title=data.get("brand_name", "") or d.id,
                subtitle=data.get("industry", "") or data.get("site_id", ""),
                on_click=ui.Call("__panel__brand_detail", brand_id=d.id),
            )
        )

    return ui.List(items=items, searchable=True)


@ext.panel(
    "brand_detail",
    slot="center",
    title="Brand Detail",
    icon="🎯",
    center_overlay=True,
)
async def brand_detail_panel(ctx, brand_id: str = "", **kwargs) -> object:
    """Detail overlay for one brand: profile, latest SWOT, latest gap analysis."""
    if not brand_id:
        return ui.Empty(message="Pick a brand from the list.", icon="🎯")

    brand_doc = await ctx.store.get("brand_profiles", brand_id)
    if not brand_doc:
        return ui.Empty(message="Brand not found.", icon="⚠️")

    data = brand_doc.data
    sections = [
        ui.Markdown(
            f"# {data.get('brand_name', '')}\n\n"
            f"**Industry:** {data.get('industry', '—')}  \n"
            f"**Mission:** {data.get('mission', '—')}  \n"
            f"**Vision:** {data.get('vision', '—')}  \n"
            f"**Value proposition:** {data.get('value_proposition', '—')}\n\n"
            + "\n".join(f"- {u}" for u in data.get("unique_selling_points", []))
        ),
    ]

    swot_page = await ctx.store.query(
        "swot_results", where={"brand_id": brand_id}, order_by="-created_at", limit=1
    )
    if swot_page.data:
        sections.append(ui.Markdown(swot_page.data[0].data.get("body", "")))

    gap_page = await ctx.store.query(
        "gap_analysis_results", where={"brand_id": brand_id}, order_by="-created_at", limit=1
    )
    if gap_page.data:
        sections.append(ui.Markdown(gap_page.data[0].data.get("body", "")))

    return ui.Stack(direction="v", gap=3, children=sections)
