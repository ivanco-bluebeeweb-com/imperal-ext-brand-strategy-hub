"""Store-document -> entity converters + SWOT/gap-analysis heuristics for
Brand Strategy Hub.

Kept separate from main.py so each @chat.function stays about the business
action, not the derivation detail. Imported one-way from main.py only.
"""
from __future__ import annotations

from schemas import (
    BrandContentHandoff, BrandProfile, CompetitorProfile,
    GapAnalysisResult, SWOTResult, TargetSegment,
)


def to_brand_profile(d) -> BrandProfile:
    data = d.data
    return BrandProfile(
        id=d.id,
        title=data.get("brand_name", "") or d.id,
        site_id=data.get("site_id", ""),
        brand_name=data.get("brand_name", ""),
        mission=data.get("mission", ""),
        vision=data.get("vision", ""),
        value_proposition=data.get("value_proposition", ""),
        tone_of_voice=data.get("tone_of_voice", ""),
        unique_selling_points=data.get("unique_selling_points", []),
        industry=data.get("industry", ""),
        content_topics=data.get("content_topics", []),
    )


def to_competitor_profile(d) -> CompetitorProfile:
    data = d.data
    return CompetitorProfile(
        id=d.id,
        title=data.get("name", "") or d.id,
        brand_id=data.get("brand_id", ""),
        name=data.get("name", ""),
        url=data.get("url", ""),
        strengths=data.get("strengths", []),
        weaknesses=data.get("weaknesses", []),
        notes=data.get("notes", ""),
    )


def to_target_segment(d) -> TargetSegment:
    data = d.data
    return TargetSegment(
        id=d.id,
        title=data.get("segment_name", "") or d.id,
        brand_id=data.get("brand_id", ""),
        segment_name=data.get("segment_name", ""),
        demographics=data.get("demographics", ""),
        psychographics=data.get("psychographics", ""),
        pain_points=data.get("pain_points", []),
        needs=data.get("needs", []),
        preferred_channels=data.get("preferred_channels", []),
    )


def to_swot_result(d) -> SWOTResult:
    data = d.data
    strengths = data.get("strengths", [])
    weaknesses = data.get("weaknesses", [])
    opportunities = data.get("opportunities", [])
    threats = data.get("threats", [])
    is_current = data.get("is_current", True)
    body = _swot_markdown(strengths, weaknesses, opportunities, threats)
    if not is_current:
        body = "_⚠ SUPERSEDED — a newer SWOT exists for this brand._\n\n" + body
    return SWOTResult(
        id=d.id,
        title=f"SWOT — {data.get('brand_id', d.id)}" + ("" if is_current else " (superseded)"),
        brand_id=data.get("brand_id", ""),
        strengths=strengths,
        weaknesses=weaknesses,
        opportunities=opportunities,
        threats=threats,
        is_current=is_current,
        superseded_at=data.get("superseded_at", ""),
        body=body,
    )


def to_gap_analysis_result(d) -> GapAnalysisResult:
    data = d.data
    gaps = data.get("gaps", [])
    recommendations = data.get("recommendations", [])
    is_current = data.get("is_current", True)
    body = _gap_markdown(gaps, recommendations)
    if not is_current:
        body = "_⚠ SUPERSEDED — a newer gap analysis exists for this segment._\n\n" + body
    return GapAnalysisResult(
        id=d.id,
        title=f"Gap analysis — {data.get('brand_id', d.id)}" + ("" if is_current else " (superseded)"),
        brand_id=data.get("brand_id", ""),
        segment_id=data.get("segment_id", ""),
        gaps=gaps,
        recommendations=recommendations,
        is_current=is_current,
        superseded_at=data.get("superseded_at", ""),
        body=body,
    )


def _swot_markdown(strengths, weaknesses, opportunities, threats) -> str:
    def _section(label, items):
        lines = [f"## {label}"]
        lines += [f"- {i}" for i in items] if items else ["- (none identified)"]
        return "\n".join(lines)

    return "\n\n".join([
        _section("Strengths", strengths),
        _section("Weaknesses", weaknesses),
        _section("Opportunities", opportunities),
        _section("Threats", threats),
    ])


def _gap_markdown(gaps, recommendations) -> str:
    lines = ["## Gaps between brand and audience"]
    lines += [f"- {g}" for g in gaps] if gaps else ["- (no gaps identified)"]
    lines.append("\n## Recommendations to fill the gap")
    lines += [f"- {r}" for r in recommendations] if recommendations else ["- (none yet)"]
    return "\n".join(lines)


def build_swot(brand: dict, competitors: list[dict]) -> tuple[list[str], list[str], list[str], list[str]]:
    """Heuristic SWOT: brand's own stated USPs/value prop become strengths;
    absence of stated fields becomes weaknesses; competitor weaknesses become
    opportunities (gaps to exploit); competitor strengths become threats.
    This is intentionally simple and transparent (no LLM call) — a human or
    Webbee reviews and edits it, this just gives a structured starting point.
    """
    strengths = list(brand.get("unique_selling_points", []))
    if brand.get("value_proposition"):
        strengths.append(f"Clear value proposition: {brand['value_proposition']}")
    if brand.get("tone_of_voice"):
        strengths.append(f"Defined tone of voice: {brand['tone_of_voice']}")

    weaknesses = []
    if not brand.get("mission"):
        weaknesses.append("No stated mission — brand narrative is incomplete")
    if not brand.get("value_proposition"):
        weaknesses.append("No clear value proposition defined")
    if not brand.get("unique_selling_points"):
        weaknesses.append("No unique selling points identified yet")

    opportunities = []
    threats = []
    for comp in competitors:
        for w in comp.get("weaknesses", []):
            opportunities.append(f"{comp.get('name', 'Competitor')} weakness to exploit: {w}")
        for s in comp.get("strengths", []):
            threats.append(f"{comp.get('name', 'Competitor')} strength to watch: {s}")

    if not competitors:
        opportunities.append("No competitors tracked yet — add some via add_brand_competitor for a sharper SWOT")
        threats.append("No competitors tracked yet — real market threats cannot be derived without them; add some via add_brand_competitor")

    return strengths, weaknesses, opportunities, threats


def build_gap_analysis(brand: dict, segment: dict) -> tuple[list[str], list[str]]:
    """Heuristic brand-vs-audience gap analysis: compares the segment's
    stated needs/pain points against what the brand currently addresses
    (its USPs + value proposition), and proposes concrete fixes for any
    unaddressed need. Simple keyword-overlap heuristic, not NLP — a
    transparent starting point for a human/Webbee review pass.
    """
    brand_text = " ".join(
        brand.get("unique_selling_points", []) + [brand.get("value_proposition", "")]
    ).lower()

    gaps = []
    for need in segment.get("needs", []):
        if need and need.lower() not in brand_text:
            gaps.append(f"Segment need not addressed by current positioning: {need}")
    for pain in segment.get("pain_points", []):
        if pain and pain.lower() not in brand_text:
            gaps.append(f"Segment pain point not addressed by current positioning: {pain}")

    if not gaps:
        gaps.append("No obvious gaps found from current data — positioning appears aligned; revisit as segment data grows")

    recommendations = []
    for gap in gaps:
        if "not addressed" in gap:
            what = gap.split(": ", 1)[-1]
            recommendations.append(f"Address '{what}' explicitly in messaging/content for this segment")
    if segment.get("preferred_channels"):
        recommendations.append(
            f"Prioritise these channels for this segment: {', '.join(segment['preferred_channels'])}"
        )

    return gaps, recommendations


def to_content_handoff(brand: dict, brand_id: str, site_id: str, domain: str, target_languages: list[str]) -> BrandContentHandoff:
    body = (
        f"# {brand.get('brand_name', site_id)} — brand context for content planning\n\n"
        f"**Mission:** {brand.get('mission', '(not set)')}\n\n"
        f"**Value proposition:** {brand.get('value_proposition', '(not set)')}\n\n"
        f"**Tone of voice:** {brand.get('tone_of_voice', '(not set)')}\n\n"
        f"**Unique selling points:** {', '.join(brand.get('unique_selling_points', [])) or '(none)'}\n\n"
        f"**Content topics:** {', '.join(brand.get('content_topics', [])) or '(none set)'}\n"
    )
    return BrandContentHandoff(
        id=brand_id,
        title=f"Content handoff — {brand.get('brand_name', site_id)}",
        brand_id=brand_id,
        site_id=site_id,
        domain=domain or site_id,
        brand_name=brand.get("brand_name", ""),
        business_description=brand.get("value_proposition", "") or brand.get("mission", ""),
        content_categories=brand.get("content_topics", []) or brand.get("unique_selling_points", []),
        cta_default="",
        target_languages=target_languages,
        body=body,
    )
