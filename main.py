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
        refresh_panels=["brands"],
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
    return ActionResult.success(
        _to_brand_profile(updated), summary="Brand profile updated.",
        refresh_panels=["brand_detail", "brands"],
    )


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
    return ActionResult.success(
        _to_competitor_profile(doc), summary=f"Competitor added: {params.name}",
        refresh_panels=["brand_detail"],
    )


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
    return ActionResult.success(
        _to_target_segment(doc), summary=f"Target segment created: {params.segment_name}",
        refresh_panels=["brand_detail"],
    )


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
    return ActionResult.success(
        _to_swot_result(doc), summary=f"SWOT analysis run for brand {params.brand_id}.",
        refresh_panels=["brand_detail"],
    )


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
    return ActionResult.success(
        _to_gap_analysis_result(doc), summary="Gap analysis run.",
        refresh_panels=["brand_detail"],
    )


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
async def brand_detail_panel(ctx, brand_id: str = "", tab: str = "profile", **kwargs) -> object:
    """Detail overlay for one brand: action bar up top, then a tab switcher
    for Profile / SWOT / Gap Analysis / Competitors / Segments. Tabs are
    plain Buttons that re-call this same panel with a `tab` param (not
    ui.Tabs) -- that component isn't proven anywhere else in this
    workspace's panels, while Button + ui.Call("__panel__...") is already
    the exact mechanism the Brands list uses to open this very panel."""
    if not brand_id:
        return ui.Empty(message="Pick a brand from the list.", icon="🎯")

    brand_doc = await ctx.store.get("brand_profiles", brand_id)
    if not brand_doc:
        return ui.Empty(message="Brand not found.", icon="⚠️")

    data = brand_doc.data
    brand_name = data.get("brand_name", "") or brand_id

    comp_page = await ctx.store.query(
        "competitor_profiles", where={"brand_id": brand_id}, order_by="-created_at", limit=200
    )
    competitors = [{"id": d.id, **d.data} for d in comp_page.data]

    seg_page = await ctx.store.query(
        "target_segments", where={"brand_id": brand_id}, order_by="-created_at", limit=200
    )
    segments = list(seg_page.data)

    swot_page = await ctx.store.query(
        "swot_results", where={"brand_id": brand_id}, order_by="-created_at", limit=1
    )
    latest_swot = swot_page.data[0].data if swot_page.data else None

    gap_page = await ctx.store.query(
        "gap_analysis_results", where={"brand_id": brand_id}, order_by="-created_at", limit=1
    )
    latest_gap = gap_page.data[0].data if gap_page.data else None

    header = ui.Header(brand_name, level=2, subtitle=data.get("industry", "") or "Brand")

    action_bar = ui.Row(
        gap=2,
        children=[
            ui.Button(
                "Run SWOT Analysis", variant="primary", icon="Sparkles",
                on_click=ui.Call("run_swot_analysis", brand_id=brand_id),
            ),
            ui.Button(
                "Run Gap Analysis", variant="secondary", icon="Target",
                on_click=ui.Send(
                    f"Запусти gap-анализ для бренда «{brand_name}» (brand_id={brand_id}) -- "
                    f"выбери подходящий целевой сегмент из list_target_segments."
                ),
            ),
            ui.Button(
                "Add competitor", variant="secondary", icon="Plus",
                on_click=ui.Send(f"Добавь конкурента бренду «{brand_name}» (brand_id={brand_id}): "),
            ),
            ui.Button(
                "Add segment", variant="secondary", icon="Users",
                on_click=ui.Send(f"Добавь целевой сегмент бренду «{brand_name}» (brand_id={brand_id}): "),
            ),
            ui.Button(
                "Send to Content Strategy Hub", variant="ghost", icon="Send",
                on_click=ui.Send(
                    f"Собери build_content_strategy_handoff для бренда «{brand_name}» "
                    f"(brand_id={brand_id}) и передай в Content Strategy Hub create_site_profile."
                ),
            ),
            ui.Button(
                "Edit profile", variant="ghost", icon="Pencil",
                on_click=ui.Send(f"Хочу обновить профиль бренда «{brand_name}» (brand_id={brand_id}): "),
            ),
        ],
    )

    # ── Profile tab ──────────────────────────────────────────────────
    profile_tab = ui.Stack(
        direction="v", gap=3,
        children=[
            ui.Card(
                title="Positioning",
                content=ui.KeyValue(
                    columns=1,
                    items=[
                        {"key": "Mission", "value": data.get("mission", "—")},
                        {"key": "Vision", "value": data.get("vision", "—")},
                        {"key": "Value proposition", "value": data.get("value_proposition", "—")},
                        {"key": "Tone of voice", "value": data.get("tone_of_voice", "—")},
                        {"key": "Site id", "value": data.get("site_id", "—")},
                    ],
                ),
            ),
            ui.Card(
                title="Unique selling points",
                content=(
                    ui.Markdown("\n".join(f"- {u}" for u in data.get("unique_selling_points", [])))
                    if data.get("unique_selling_points") else
                    ui.Empty(message="No USPs recorded yet.", icon="—")
                ),
            ),
        ],
    )

    # ── SWOT tab ─────────────────────────────────────────────────────
    if latest_swot:
        swot_tab = ui.Grid(
            columns=2, gap=3,
            children=[
                ui.Card(title="Strengths", content=_swot_list(latest_swot.get("strengths", []))),
                ui.Card(title="Weaknesses", content=_swot_list(latest_swot.get("weaknesses", []))),
                ui.Card(title="Opportunities", content=_swot_list(latest_swot.get("opportunities", []))),
                ui.Card(title="Threats", content=_swot_list(latest_swot.get("threats", []))),
            ],
        )
    else:
        swot_tab = ui.Empty(message="No SWOT analysis yet -- run one from the action bar above.", icon="Sparkles")

    # ── Gap analysis tab ─────────────────────────────────────────────
    if latest_gap:
        gap_tab = ui.Stack(
            direction="v", gap=3,
            children=[
                ui.Card(title="Gaps between brand and audience", content=_swot_list(latest_gap.get("gaps", []))),
                ui.Card(title="Recommendations to fill the gap", content=_swot_list(latest_gap.get("recommendations", []))),
            ],
        )
    else:
        gap_tab = ui.Empty(message="No gap analysis yet -- run one from the action bar above.", icon="Target")

    # ── Competitors tab ──────────────────────────────────────────────
    if competitors:
        comp_items = [
            ui.ListItem(
                id=c.get("id", ""),
                title=c.get("name", ""),
                subtitle=c.get("url", ""),
                meta=f"{len(c.get('strengths', []))} strengths · {len(c.get('weaknesses', []))} weaknesses",
            )
            for c in competitors
        ]
        competitors_tab = ui.List(items=comp_items, searchable=True)
    else:
        competitors_tab = ui.Empty(message="No competitors tracked yet.", icon="Users")

    # ── Segments tab ─────────────────────────────────────────────────
    if segments:
        seg_items = [
            ui.ListItem(
                id=d.id,
                title=d.data.get("segment_name", "") or d.id,
                subtitle=d.data.get("demographics", ""),
                meta=f"{len(d.data.get('pain_points', []))} pain points · {len(d.data.get('needs', []))} needs",
            )
            for d in segments
        ]
        segments_tab = ui.List(items=seg_items, searchable=True)
    else:
        segments_tab = ui.Empty(message="No target segments defined yet.", icon="Users")

    tab_defs = [
        ("profile", "Profile", profile_tab),
        ("swot", "SWOT", swot_tab),
        ("gap", "Gap Analysis", gap_tab),
        ("competitors", f"Competitors ({len(competitors)})", competitors_tab),
        ("segments", f"Segments ({len(segments)})", segments_tab),
    ]
    active_tab = tab if tab in {t[0] for t in tab_defs} else "profile"

    tab_switcher = ui.Row(
        gap=2,
        children=[
            ui.Button(
                label,
                variant="primary" if key == active_tab else "ghost",
                size="sm",
                on_click=ui.Call("__panel__brand_detail", brand_id=brand_id, tab=key),
            )
            for key, label, _content in tab_defs
        ],
    )
    active_content = next(content for key, _label, content in tab_defs if key == active_tab)

    return ui.Stack(
        direction="v", gap=3,
        children=[header, action_bar, ui.Divider(), tab_switcher, active_content],
    )


def _swot_list(items: list) -> object:
    if not items:
        return ui.Empty(message="(none identified)", icon="—")
    return ui.Markdown("\n".join(f"- {i}" for i in items))
