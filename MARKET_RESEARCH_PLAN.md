
# Market Research — development plan (not started)

**Created:** 2026-08-17
**Product:** Brand Strategy Hub → Market Research capability.
**Status:** Planning only. No code written yet — explicitly deferred until the owner says go.
**Source case:** G4S.md lead-generation review (2026-08-17) — see Vikunja task #1846 (project *BBW Imperal Apps*) and the "G4S — лиды" note for the full walkthrough that surfaced this gap.

---

## Why this belongs in Brand Strategy Hub, not a new app

Earlier drafts of this gap-analysis proposed a separate app for "market research". The owner corrected that: market research is squarely brand-strategy work — it feeds directly into `run_gap_analysis` and `run_swot_analysis`, which already live here. Splitting it into another app would just add IPC overhead for something that belongs next to the brand profile it's about.

What does **not** belong here (moved elsewhere, see below):
- Sales-side prospecting/outreach, lead capture, CRM bridging → proposed **Sales Strategy Hub** (separate concept doc, see `sales-strategy-hub-plan.md` at the workspace root).
- Tender/procurement monitoring → explicitly **not** a dedicated feature anywhere (see "Tender monitoring — decision" below).
- Domain/brand name-collision detection (e.g. g4s.md vs the international G4S security company) → stays a candidate for `seo-audit-engine` (tracked separately, Vikunja #1855), unrelated to this plan.

## The actual gap today

`run_gap_analysis` and `run_swot_analysis` only reason over data **already stored** in the system: the brand's own profile plus a target segment. Neither one goes out and looks at the real market. Everything about market landscape, fragmentation, and who the actual competitors are came from manual `web_search` calls during the G4S.md review — not from any Brand Strategy Hub tool.

`add_brand_competitor` / `list_brand_competitors` already exist, but they are a manual recording form: something (a human, or me in chat) has to find the competitor out in the world first and then type it in. There is no discovery step.

## Proposed shape (draft — to be refined before implementation)

- **New entity: `MarketResearchSnapshot`** — versioned per brand (current + superseded, same pattern as SWOT snapshots), holding: a market-landscape summary, a *candidate* competitor list (not yet promoted to tracked competitors), industry/geography context notes, and the sourcing trail (queries used / URLs read) so a reviewer can see where each claim came from.
- **New tool: `run_market_research(brand_id, ...)`** — uses the `web-search` app (web_search + read_url) grounded to the brand's own industry/geography fields (already on the brand profile), and writes a draft snapshot. It does **not** auto-write into `add_brand_competitor` — a human reviews the candidate list and promotes the real ones, same human-in-the-loop philosophy as VBS evidence review. This avoids polluting tracked competitors with search noise.
- **Feed-through:** `run_gap_analysis` / `run_swot_analysis` should optionally read the latest *current* `MarketResearchSnapshot` for a brand, if one exists, so their output is grounded in real market context instead of only the brand's own stated profile.

## Explicit non-goals

- Not a standing/scheduled monitoring feed — it's a callable, on-demand research pass a human or agent triggers when working a brand, not a background job.
- Not a tender scraper (see decision below).
- Not a lead database or CRM — that's Sales Strategy Hub's job, and the two are meant to compose, not merge.

## Tender monitoring — decision (documented here for traceability)

Originally proposed as its own module/app. Owner's call: tender/procurement monitoring is a **special case** of B2B lead sourcing — real, but narrow enough that it doesn't justify dedicated engineering (a scheduled scraper, a new data model, ongoing maintenance of portal-specific parsing).

**Decision:** no dedicated tender-monitoring feature is planned, anywhere. If a tender opportunity becomes relevant during real pipeline work on a brand (e.g. while reviewing market research for a client with public-sector target objects like schools/kindergartens), it gets **noticed and handled manually in the moment** — a `web_search` call plus logging the finding as a normal task/lead, not a standing automated system. This is a conscious low-priority decision, not an oversight; see Vikunja #1852 for the down-scoped tracking entry.

## Delivery ledger

Nothing implemented yet. This section stays empty until work actually starts — do not check anything off ahead of the code.

## Open questions before implementation starts

- How to bound the cost/scope of `run_market_research` per call (one-shot per review cycle vs. something more granular)?
- How should geography/language grounding work when the brand profile doesn't state a country explicitly?
- Exact promotion flow from "candidate competitor in a snapshot" → `add_brand_competitor` (one call per candidate? a bulk-accept action?).
