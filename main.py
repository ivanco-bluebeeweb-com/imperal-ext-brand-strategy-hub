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

from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit
import hashlib
import ipaddress
import json

from imperal_sdk import ActionResult, Extension, ChatExtension, ui

from schemas import (
    AddCompetitorParams, ActivateVisualBrandSystemParams, ActivateVisualProfileParams,
    BuildContentStrategyHandoffParams, CreateBrandProfileParams, CreateVisualProfileParams,
    InitializeVisualBrandWorkspaceParams, MigrateVisualBrandAccessParams,
    CreateTargetSegmentParams, CreateVisualBrandSystemParams,
    ListBrandProfilesParams, ListCompetitorsParams, ListGapAnalysesParams,
    ListSWOTResultsParams, ListTargetSegmentsParams, ListVisualBrandAuditEventsParams,
    VerifyVisualBrandAuditIntegrityParams, AcknowledgeVisualBrandAuditIncidentParams,
    ListVisualBrandAuditIncidentsParams,
    ListVisualBrandSystemsParams, ListVisualEvidenceParams, ListVisualProfilesParams,
    RegisterVisualEvidenceParams, ReviewVisualEvidenceParams, ResolveCurrentVisualProfileParams, RunGapAnalysisParams, RunSWOTAnalysisParams,
    ListBrandMembershipsParams, SetBrandMembershipParams, RevokeBrandMembershipParams,
    UpdateBrandProfileParams,
    AuditEvent, AuditEventList, AuditIntegrity, AuditIntegrityIncident, AuditIntegrityIncidentList, BrandContentHandoff,
    BrandProfile, BrandProfileList, BrandMembership, BrandMembershipList, VisualBrandSystem, VisualBrandSystemList,
    VisualBrandWorkspace, VisualEvidence, VisualEvidenceList, VisualProfile, VisualProfileList,
    ConnectedSite, ConnectedSiteList, ListConnectedSitesParams,
    CompetitorProfile, CompetitorProfileList,
    GapAnalysisResult, GapAnalysisResultList,
    SWOTResult, SWOTResultList,
    TargetSegment, TargetSegmentList,
    DeleteResult, DeleteBrandProfileParams, DeleteCompetitorParams,
    DeleteTargetSegmentParams, ArchiveSWOTResultParams,
    ArchiveGapAnalysisParams, PurgeBrandStrategyDataParams, PurgeResult,
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


VBS_WORKSPACES = "vbs_workspaces"
VBS_SYSTEMS = "visual_brand_systems"
VBS_AUDIT_EVENTS = "visual_brand_audit_events"
VBS_AUDIT_INCIDENTS = "visual_brand_audit_integrity_incidents"
VBS_EVIDENCE = "visual_evidence"
VBS_PROFILES = "visual_profiles"
VBS_MEMBERSHIPS = "vbs_brand_memberships"


def _actor(ctx) -> tuple[str, str]:
    """Return the authenticated user and tenant without trusting panel input."""
    user = getattr(ctx, "user", None)
    return (
        getattr(user, "imperal_id", "") or "",
        getattr(user, "tenant_id", "") or "",
    )


async def _workspace_for_brand(ctx, brand_id: str):
    """Load the one VBS workspace bound to a brand, if initialized."""
    page = await ctx.store.query(VBS_WORKSPACES, where={"brand_id": brand_id}, limit=2)
    return page.data[0] if page.data else None


ROLE_PERMISSIONS = {
    "owner": {"read", "edit", "review", "manage_access"},
    "editor": {"read", "edit"},
    "reviewer": {"read", "review"},
    "viewer": {"read"},
}


async def _membership_for_actor(ctx, workspace):
    """Resolve an active tenant-local membership; ordinary ACL never trusts legacy owner fields."""
    actor_id, tenant_id = _actor(ctx)
    if not actor_id or not tenant_id or workspace.data.get("tenant_id") != tenant_id:
        return None
    page = await ctx.store.query(VBS_MEMBERSHIPS, where={"brand_id": workspace.data["brand_id"]}, limit=200)
    return next((item.data for item in page.data if item.data.get("tenant_id") == tenant_id and item.data.get("user_id") == actor_id and item.data.get("status") == "active"), None)


async def _require_vbs_access(ctx, brand_id: str, permission: str = "read"):
    """Enforce private tenant membership and one server-side role permission per VBS action."""
    workspace = await _workspace_for_brand(ctx, brand_id)
    if not workspace:
        return None, None, ActionResult.error(
            "The VBS workspace is not initialized for this brand. Initialize it explicitly first.",
            retryable=False,
            code="VBS_WORKSPACE_NOT_INITIALIZED",
        )
    membership = await _membership_for_actor(ctx, workspace)
    if not membership or permission not in ROLE_PERMISSIONS.get(membership.get("role", ""), set()):
        return None, None, ActionResult.error(
            "You do not have the required access to this brand's VBS workspace.",
            retryable=False,
            code="VBS_ACCESS_DENIED",
        )
    return workspace, membership, None


async def _require_vbs_workspace_owner(ctx, brand_id: str):
    """Compatibility wrapper for remaining P0 reads; new actions use explicit permissions."""
    workspace, _membership, error = await _require_vbs_access(ctx, brand_id, "read")
    return workspace, error


async def _active_memberships(ctx, workspace):
    """Return every active membership for one tenant-local workspace, including its legacy owner."""
    page = await ctx.store.query(VBS_MEMBERSHIPS, where={"brand_id": workspace.data["brand_id"]}, limit=200)
    records = [item for item in page.data if item.data.get("tenant_id") == workspace.data["tenant_id"] and item.data.get("status") == "active"]
    return [{"id": item.id, "data": item.data} for item in records]


async def _advance_vbs_workspace(ctx, workspace, expected_version: int):
    """Advance the workspace version only when the caller still holds its snapshot.

    Store updates have no conditional-write primitive, so re-read immediately
    before each state mutation. This makes stale UI submissions fail closed;
    the later storage-concurrency spike will replace this with a native CAS
    primitive if the platform exposes one.
    """
    latest = await ctx.store.get(VBS_WORKSPACES, workspace.id)
    if not latest or latest.data.get("version") != expected_version:
        return None, ActionResult.error(
            "The VBS workspace changed since you opened it. Refresh and review before saving.",
            retryable=True,
            code="VBS_STALE_WORKSPACE",
        )
    updated = await ctx.store.update(
        VBS_WORKSPACES,
        latest.id,
        {**latest.data, "version": expected_version + 1, "updated_at": _now_iso()},
    )
    return updated, None


def _profile_snapshot_hash(vbs, evidence_records, profile_summary: str, art_direction: str) -> str:
    """Hash a canonical, non-personal baseline so downstream resolution is auditable."""
    payload = {
        "vbs": {
            "id": vbs.id,
            "revision": vbs.data.get("revision"),
            "visual_intent": vbs.data.get("visual_intent", ""),
            "realism_level": vbs.data.get("realism_level", ""),
            "core_rules": vbs.data.get("core_rules", []),
            "prohibited_patterns": vbs.data.get("prohibited_patterns", []),
        },
        "evidence": [
            {
                "id": record.id,
                "source_url": record.data.get("source_url", ""),
                "source_title": record.data.get("source_title", ""),
                "observation": record.data.get("observation", ""),
                "status": record.data.get("status", ""),
            }
            for record in sorted(evidence_records, key=lambda item: item.id)
        ],
        "profile_summary": profile_summary,
        "art_direction": art_direction,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_public_https_reference(raw_url: str) -> tuple[str | None, str | None]:
    """Accept only a canonical public HTTPS reference; never resolve or fetch it.

    DNS hostnames are deliberately retained because resolving them here can
    create its own network side effect and TOCTOU window. A later fetcher must
    resolve and re-check each destination immediately before connecting.
    """
    value = raw_url.strip()
    if not value or any(char.isspace() for char in value):
        return None, "Provide a single HTTPS URL without whitespace."
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None, "Provide a valid HTTPS URL."
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        return None, "Only HTTPS reference URLs are allowed."
    if parsed.username or parsed.password:
        return None, "Reference URLs cannot contain embedded credentials."
    try:
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return None, "Reference URL has an invalid host or port."
    if not host or host.lower() == "localhost" or port not in (None, 443):
        return None, "Reference URL must use a public host and standard HTTPS port."
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        address = None
    if address and (not address.is_global):
        return None, "Reference URL cannot target a private, loopback, or reserved IP address."
    if parsed.fragment:
        return None, "Reference URLs cannot include fragments."
    return urlunsplit(("https", parsed.netloc.lower(), parsed.path or "/", parsed.query, "")), None


def _audit_event_hash(payload: dict) -> str:
    """Return a canonical seal for one audit event's immutable application fields."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _append_vbs_audit(ctx, *, brand_id: str, vbs_id: str, event_type: str, details: str) -> None:
    """Append a chained audit event and advance its workspace-local integrity anchor."""
    workspace = await _workspace_for_brand(ctx, brand_id)
    if not workspace:
        raise ValueError("VBS workspace must exist before appending an audit event.")
    actor_id, tenant_id = _actor(ctx)
    occurred_at = _now_iso()
    sequence = int(workspace.data.get("audit_chain_sequence", 0)) + 1
    previous_hash = workspace.data.get("audit_chain_head", "")
    payload = {
        "brand_id": brand_id,
        "vbs_id": vbs_id,
        "event_type": event_type,
        "actor_id": actor_id,
        "tenant_id": tenant_id,
        "details": details,
        "occurred_at": occurred_at,
        "chain_sequence": sequence,
        "previous_integrity_hash": previous_hash,
    }
    integrity_hash = _audit_event_hash(payload)
    await ctx.store.create(VBS_AUDIT_EVENTS, {**payload, "integrity_hash": integrity_hash, "integrity_version": 2})
    await ctx.store.update(VBS_WORKSPACES, workspace.id, {
        **workspace.data,
        "audit_chain_head": integrity_hash,
        "audit_chain_sequence": sequence,
        "audit_chain_started_at": workspace.data.get("audit_chain_started_at") or occurred_at,
    })


def _audit_integrity_result(workspace, events, sealed, chained, valid, message, invalid_event_id="") -> AuditIntegrity:
    return AuditIntegrity(
        id=f"audit-integrity:{workspace.data['brand_id']}", title="VBS audit integrity",
        brand_id=workspace.data["brand_id"], tenant_id=workspace.data["tenant_id"],
        checked_events=len(events), sealed_events=sealed, chained_events=chained,
        chain_head=workspace.data.get("audit_chain_head", ""),
        chain_sequence=int(workspace.data.get("audit_chain_sequence", 0)),
        valid=valid, first_invalid_event_id=invalid_event_id, message=message,
    )


async def _verify_vbs_audit_integrity(ctx, workspace) -> AuditIntegrity:
    """Verify record seals plus the v2 ordered chain against its workspace anchor."""
    page = await ctx.store.query(VBS_AUDIT_EVENTS, where={"brand_id": workspace.data["brand_id"]}, order_by="occurred_at", limit=500)
    events = [item for item in page.data if item.data.get("tenant_id") == workspace.data["tenant_id"]]
    sealed = 0
    chained = 0
    previous_hash = ""
    expected_sequence = 1
    chained_events = [item for item in events if item.data.get("integrity_version") == 2]
    for item in events:
        stored_hash = item.data.get("integrity_hash", "")
        if not stored_hash:
            continue
        sealed += 1
        if item.data.get("integrity_version") != 2:
            payload = {key: item.data.get(key, "") for key in ("brand_id", "vbs_id", "event_type", "actor_id", "tenant_id", "details", "occurred_at")}
            if _audit_event_hash(payload) != stored_hash:
                return _audit_integrity_result(workspace, events, sealed, chained, False, "A sealed audit event does not match its recorded integrity hash.", item.id)
            continue
        chained += 1
        payload = {key: item.data.get(key, "") for key in ("brand_id", "vbs_id", "event_type", "actor_id", "tenant_id", "details", "occurred_at", "chain_sequence", "previous_integrity_hash")}
        if _audit_event_hash(payload) != stored_hash:
            return _audit_integrity_result(workspace, events, sealed, chained, False, "A chained audit event does not match its recorded integrity hash.", item.id)
        if item.data.get("chain_sequence") != expected_sequence or item.data.get("previous_integrity_hash", "") != previous_hash:
            return _audit_integrity_result(workspace, events, sealed, chained, False, "The ordered audit hash chain is missing or out of sequence.", item.id)
        previous_hash = stored_hash
        expected_sequence += 1
    if chained_events and (workspace.data.get("audit_chain_head", "") != previous_hash or workspace.data.get("audit_chain_sequence", 0) != chained):
        return _audit_integrity_result(workspace, events, sealed, chained, False, "The workspace audit-chain anchor does not match the recorded audit trail.")
    message = "All sealed audit events passed integrity verification."
    if chained:
        message += f" {chained} event(s) are protected by the ordered audit hash chain."
    if sealed < len(events):
        message += f" {len(events) - sealed} unsealed legacy event(s) predate integrity sealing and are reported but not cryptographically verifiable."
    if sealed > chained:
        message += f" {sealed - chained} sealed v1 event(s) predate the audit chain and remain individually verified only."
    return _audit_integrity_result(workspace, events, sealed, chained, True, message)

async def _require_vbs_audit_integrity(ctx, workspace):
    """Fail closed before critical mutations if a sealed audit record was changed."""
    integrity = await _verify_vbs_audit_integrity(ctx, workspace)
    if not integrity.valid:
        return ActionResult.error(
            "A sealed VBS audit event failed integrity verification. Critical changes are paused; investigate the audit trail before continuing.",
            retryable=False,
            code="VBS_AUDIT_INTEGRITY_FAILED",
        )
    return None


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
# Cross-app site discovery for Quick Add -- not just WordPress, on purpose.
# ──────────────────────────────────────────────────────────────────────────
# Registry of app_ids that expose a "list_connected_sites" IPC method
# returning [{"site_id", "name", "url", "status"}, ...]. Any future site
# provider (Shopify, Webflow, a plain-domain connector, ...) is added here
# and Quick Add picks it up automatically -- no panel code changes needed.
SITE_PROVIDER_APP_IDS: list[str] = ["wp-site-connector"]


def _canonical_site_id(row: dict) -> str:
    """Normalise a provider's site identifier to its bare domain.

    Providers name sites their own way -- WordPress Hub uses a slug
    ('g4s-md') while this app keys sites by domain ('g4s.md'). Quick Add must
    speak the domain form, otherwise clicking it would create a DUPLICATE
    profile next to the existing one and 'already added' checks would miss.
    """
    host = (row.get("url") or "").strip().split("://", 1)[-1].split("/", 1)[0].lower()
    if host.startswith("www."):
        host = host[4:]
    return host or (row.get("site_id") or "")


async def fetch_connected_sites(ctx) -> tuple[list[dict], list[dict]]:
    """Pull every connected site from every registered site-provider
    extension via ctx.extensions.call -- direct in-process IPC (no chat
    round-trip, no manual site_id typing).

    Returns (sites, problems). A provider that fails is reported in
    `problems` as {"provider", "reason"} instead of vanishing: the Quick Add
    card then SHOWS why it is empty, so the failure is visible and fixable
    in the UI rather than silently hiding the whole feature.
    """
    sites: list[dict] = []
    problems: list[dict] = []
    for app_id in SITE_PROVIDER_APP_IDS:
        try:
            rows = await ctx.extensions.call(app_id, "list_connected_sites")
        except Exception as exc:  # noqa: BLE001 -- surfaced to the panel, not swallowed
            problems.append({
                "provider": app_id,
                "reason": f"{type(exc).__name__}: {exc}".strip()[:300],
            })
            continue
        for r in rows or []:
            sites.append({
                **r,
                "provider": app_id,
                "provider_site_id": r.get("site_id", ""),
                "site_id": _canonical_site_id(r),
            })
    return sites, problems


# ──────────────────────────────────────────────────────────────────────────
# Visual Brand System — P0 non-personal vertical slice
# ──────────────────────────────────────────────────────────────────────────

@chat.function(
    "initialize_visual_brand_workspace",
    description=(
        "Explicitly initialize a private VBS workspace for one existing brand. "
        "Required once before creating or reading VBS revisions for a legacy brand."
    ),
    action_type="write",
    effects=["create:visual_brand_workspace"],
    event="brand-strategy-hub.initialize_visual_brand_workspace",
    data_model=VisualBrandWorkspace,
)
async def initialize_visual_brand_workspace(ctx, params: InitializeVisualBrandWorkspaceParams) -> ActionResult[VisualBrandWorkspace]:
    """Claim a legacy brand deliberately; never bind it to the first casual reader."""
    if not params.confirm_owner_claim:
        return ActionResult.error(
            "Explicit owner confirmation is required before initializing this VBS workspace.",
            retryable=False,
            code="VBS_OWNER_CLAIM_REQUIRED",
        )
    actor_id, tenant_id = _actor(ctx)
    if not actor_id or not tenant_id:
        return ActionResult.error(
            "An authenticated tenant context is required to initialize a VBS workspace.",
            retryable=False,
            code="VBS_AUTH_CONTEXT_REQUIRED",
        )
    brand = await ctx.store.get("brand_profiles", params.brand_id)
    if not brand:
        return ActionResult.error("Brand profile not found.", retryable=False, code="BRAND_NOT_FOUND")

    workspace = await _workspace_for_brand(ctx, params.brand_id)
    if workspace:
        data = workspace.data
        if data.get("tenant_id") == tenant_id and data.get("owner_id") == actor_id:
            return ActionResult.success(
                {"workspace_id": workspace.id, "brand_id": params.brand_id, "version": data.get("version", 1)},
                "VBS workspace is already initialized for you.",
                refresh_panels=["brand_detail"],
            )
        return ActionResult.error(
            "A VBS workspace for this brand is already owned by another tenant or user.",
            retryable=False,
            code="VBS_WORKSPACE_ALREADY_CLAIMED",
        )

    workspace = await ctx.store.create(
        VBS_WORKSPACES,
        {
            "brand_id": params.brand_id,
            "tenant_id": tenant_id,
            "owner_id": actor_id,
            "version": 1,
            "access_model_version": 2,
            "status": "ready",
            "created_at": _now_iso(),
        },
    )
    await ctx.store.create(
        VBS_MEMBERSHIPS,
        {
            "brand_id": params.brand_id,
            "tenant_id": tenant_id,
            "user_id": actor_id,
            "role": "owner",
            "status": "active",
            "created_by": actor_id,
            "created_at": _now_iso(),
        },
    )
    await _append_vbs_audit(
        ctx,
        brand_id=params.brand_id,
        vbs_id="",
        event_type="workspace_initialized",
        details="Explicit owner claim created the P0 VBS workspace.",
    )
    return ActionResult.success(
        {"workspace_id": workspace.id, "brand_id": params.brand_id, "version": 1},
        "VBS workspace initialized. You can now create its first draft.",
        refresh_panels=["brand_detail"],
    )


@chat.function(
    "migrate_visual_brand_access",
    description="Explicitly migrate one legacy VBS workspace from its founding owner field to the P0 membership access model.",
    action_type="write",
    effects=["create:brand_membership", "update:vbs_workspace"],
    event="brand-strategy-hub.migrate_visual_brand_access",
    data_model=VisualBrandWorkspace,
)
async def migrate_visual_brand_access(ctx, params: MigrateVisualBrandAccessParams) -> ActionResult[VisualBrandWorkspace]:
    """Perform the one-time, owner-confirmed legacy ACL migration without touching VBS content."""
    workspace = await _workspace_for_brand(ctx, params.brand_id)
    if not workspace:
        return ActionResult.error("The VBS workspace is not initialized for this brand.", retryable=False, code="VBS_WORKSPACE_NOT_INITIALIZED")
    actor_id, tenant_id = _actor(ctx)
    if (
        not actor_id
        or not tenant_id
        or workspace.data.get("tenant_id") != tenant_id
        or workspace.data.get("owner_id") != actor_id
    ):
        return ActionResult.error("Only this legacy workspace's founding owner in its tenant may migrate access.", retryable=False, code="VBS_ACCESS_DENIED")
    if workspace.data.get("version") != params.expected_workspace_version:
        return ActionResult.error("The VBS workspace changed. Refresh before migrating access.", retryable=True, code="VBS_STALE_WORKSPACE")
    integrity_error = await _require_vbs_audit_integrity(ctx, workspace)
    if integrity_error:
        return integrity_error
    page = await ctx.store.query(VBS_MEMBERSHIPS, where={"brand_id": params.brand_id}, limit=200)
    owner_membership = next((item for item in page.data if item.data.get("tenant_id") == tenant_id and item.data.get("user_id") == actor_id and item.data.get("status") == "active"), None)
    if workspace.data.get("access_model_version", 1) >= 2 and owner_membership:
        return ActionResult.success(
            VisualBrandWorkspace(id=workspace.id, title=params.brand_id, **workspace.data),
            "VBS access already uses the membership model.",
            refresh_panels=["brand_detail"],
        )
    advanced, error = await _advance_vbs_workspace(ctx, workspace, params.expected_workspace_version)
    if error:
        return error
    if not owner_membership:
        await ctx.store.create(
            VBS_MEMBERSHIPS,
            {
                "brand_id": params.brand_id,
                "tenant_id": tenant_id,
                "user_id": actor_id,
                "role": "owner",
                "status": "active",
                "workspace_version": advanced.data["version"],
                "created_by": actor_id,
                "created_at": _now_iso(),
            },
        )
    migrated = await ctx.store.update(
        VBS_WORKSPACES,
        advanced.id,
        {**advanced.data, "access_model_version": 2, "access_model_migrated_at": _now_iso()},
    )
    await _append_vbs_audit(
        ctx,
        brand_id=params.brand_id,
        vbs_id="",
        event_type="membership_model_migrated",
        details="Migrated the legacy founding-owner access record to one active owner membership.",
    )
    return ActionResult.success(
        VisualBrandWorkspace(id=migrated.id, title=params.brand_id, **migrated.data),
        "VBS access migrated to the membership model.",
        refresh_panels=["brand_detail"],
    )


@chat.function("list_brand_memberships", description="List active private VBS brand memberships for an initialized workspace.")
async def list_brand_memberships(ctx, params: ListBrandMembershipsParams) -> ActionResult[BrandMembershipList]:
    """List tenant-local roles without exposing memberships from another workspace."""
    workspace, _membership, error = await _require_vbs_access(ctx, params.brand_id, "read")
    if error:
        return error
    records = await _active_memberships(ctx, workspace)
    items = [BrandMembership(id=item["id"], title=item["data"]["user_id"], **item["data"]) for item in records]
    return ActionResult.success(BrandMembershipList(items=items), f"Found {len(items)} active brand membership(s).")


@chat.function(
    "set_brand_membership",
    description="Add or update a tenant-local VBS brand role for a known Imperal user ID.",
    action_type="write",
    effects=["create_or_update:brand_membership"],
    event="brand-strategy-hub.set_brand_membership",
    data_model=BrandMembership,
)
async def set_brand_membership(ctx, params: SetBrandMembershipParams) -> ActionResult[BrandMembership]:
    """Grant or change a role, guarded by owner permission and a workspace version."""
    if params.role not in ROLE_PERMISSIONS:
        return ActionResult.error("Role must be owner, editor, reviewer, or viewer.", retryable=False, code="VBS_ROLE_INVALID")
    workspace, _membership, error = await _require_vbs_access(ctx, params.brand_id, "manage_access")
    if error:
        return error
    if params.user_id == workspace.data.get("owner_id") and params.role != "owner":
        return ActionResult.error("The workspace's founding owner remains an owner in P0.", retryable=False, code="VBS_LAST_OWNER_PROTECTED")
    if workspace.data.get("version") != params.expected_workspace_version:
        return ActionResult.error("The VBS workspace changed. Refresh before changing access.", retryable=True, code="VBS_STALE_WORKSPACE")
    integrity_error = await _require_vbs_audit_integrity(ctx, workspace)
    if integrity_error:
        return integrity_error
    actor_id, tenant_id = _actor(ctx)
    page = await ctx.store.query(VBS_MEMBERSHIPS, where={"brand_id": params.brand_id}, limit=200)
    existing = next((item for item in page.data if item.data.get("tenant_id") == tenant_id and item.data.get("user_id") == params.user_id), None)
    advanced, error = await _advance_vbs_workspace(ctx, workspace, params.expected_workspace_version)
    if error:
        return error
    data = {"brand_id": params.brand_id, "tenant_id": tenant_id, "user_id": params.user_id, "role": params.role, "status": "active", "workspace_version": advanced.data["version"], "created_by": actor_id, "updated_at": _now_iso()}
    record = await ctx.store.update(VBS_MEMBERSHIPS, existing.id, {**existing.data, **data}) if existing else await ctx.store.create(VBS_MEMBERSHIPS, {**data, "created_at": _now_iso()})
    await _append_vbs_audit(ctx, brand_id=params.brand_id, vbs_id="", event_type="membership_set", details=f"Set {params.user_id} role to {params.role}.")
    return ActionResult.success(BrandMembership(id=record.id, title=params.user_id, **record.data), "Brand membership saved.", refresh_panels=["brand_detail"])


@chat.function(
    "revoke_brand_membership",
    description="Revoke an active tenant-local VBS brand membership while preserving the final owner.",
    action_type="write",
    effects=["update:brand_membership"],
    event="brand-strategy-hub.revoke_brand_membership",
    data_model=BrandMembership,
)
async def revoke_brand_membership(ctx, params: RevokeBrandMembershipParams) -> ActionResult[BrandMembership]:
    """Revoke access fail-closed; the legacy workspace owner cannot be removed in P0."""
    workspace, _membership, error = await _require_vbs_access(ctx, params.brand_id, "manage_access")
    if error:
        return error
    if params.user_id == workspace.data.get("owner_id"):
        return ActionResult.error("The workspace's founding owner cannot be revoked in P0.", retryable=False, code="VBS_LAST_OWNER_PROTECTED")
    if workspace.data.get("version") != params.expected_workspace_version:
        return ActionResult.error("The VBS workspace changed. Refresh before changing access.", retryable=True, code="VBS_STALE_WORKSPACE")
    integrity_error = await _require_vbs_audit_integrity(ctx, workspace)
    if integrity_error:
        return integrity_error
    actor_id, tenant_id = _actor(ctx)
    page = await ctx.store.query(VBS_MEMBERSHIPS, where={"brand_id": params.brand_id}, limit=200)
    record = next((item for item in page.data if item.data.get("tenant_id") == tenant_id and item.data.get("user_id") == params.user_id and item.data.get("status") == "active"), None)
    if not record:
        return ActionResult.error("Active brand membership not found.", retryable=False, code="VBS_MEMBERSHIP_NOT_FOUND")
    active_owners = [item for item in await _active_memberships(ctx, workspace) if item["data"].get("role") == "owner"]
    if record.data.get("role") == "owner" and len(active_owners) <= 1:
        return ActionResult.error("At least one active owner must remain.", retryable=False, code="VBS_LAST_OWNER_PROTECTED")
    advanced, error = await _advance_vbs_workspace(ctx, workspace, params.expected_workspace_version)
    if error:
        return error
    updated = await ctx.store.update(VBS_MEMBERSHIPS, record.id, {**record.data, "status": "revoked", "workspace_version": advanced.data["version"], "revoked_by": actor_id, "revoked_at": _now_iso()})
    await _append_vbs_audit(ctx, brand_id=params.brand_id, vbs_id="", event_type="membership_revoked", details=f"Revoked {params.user_id} access.")
    return ActionResult.success(BrandMembership(id=updated.id, title=params.user_id, **updated.data), "Brand membership revoked.", refresh_panels=["brand_detail"])


@chat.function(
    "create_visual_brand_system",
    description=(
        "Create the next draft revision of a brand's Visual Brand System. "
        "This P0 function accepts non-personal strategic rules only."
    ),
    action_type="write",
    effects=["create:visual_brand_system"],
    event="brand-strategy-hub.create_visual_brand_system",
    data_model=VisualBrandSystem,
)
async def create_visual_brand_system(ctx, params: CreateVisualBrandSystemParams) -> ActionResult[VisualBrandSystem]:
    """Create the next private VBS draft revision with stale-write protection."""
    workspace, _membership, error = await _require_vbs_access(ctx, params.brand_id, "edit")
    if error:
        return error
    if workspace.data.get("version") != params.expected_workspace_version:
        return ActionResult.error(
            "The VBS workspace changed since you opened it. Refresh and review before saving.",
            retryable=True,
            code="VBS_STALE_WORKSPACE",
        )
    advanced_workspace, error = await _advance_vbs_workspace(
        ctx, workspace, params.expected_workspace_version
    )
    if error:
        return error

    existing_page = await ctx.store.query(
        VBS_SYSTEMS, where={"brand_id": params.brand_id}, order_by="-created_at", limit=200
    )
    revisions = [d for d in existing_page.data if d.data.get("tenant_id") == workspace.data["tenant_id"]]
    revision = max((int(d.data.get("revision", 0)) for d in revisions), default=0) + 1
    actor_id, tenant_id = _actor(ctx)
    vbs = await ctx.store.create(
        VBS_SYSTEMS,
        {
            "brand_id": params.brand_id,
            "revision": revision,
            "status": "draft",
            "visual_intent": params.visual_intent.strip(),
            "realism_level": params.realism_level.strip(),
            "core_rules": [rule.strip() for rule in params.core_rules if rule.strip()],
            "prohibited_patterns": [item.strip() for item in params.prohibited_patterns if item.strip()],
            "change_note": params.change_note.strip(),
            "created_by": actor_id,
            "tenant_id": tenant_id,
            "supersedes_vbs_id": "",
            "created_at": _now_iso(),
        },
    )
    await _append_vbs_audit(
        ctx,
        brand_id=params.brand_id,
        vbs_id=vbs.id,
        event_type="vbs_draft_created",
        details=f"Created revision {revision} as a draft.",
    )
    return ActionResult.success(
        {
            "vbs_id": vbs.id,
            "brand_id": params.brand_id,
            "revision": revision,
            "status": "draft",
            "workspace_version": advanced_workspace.data["version"],
        },
        f"Created VBS revision {revision} as a draft.",
        refresh_panels=["brand_detail"],
    )


@chat.function("list_visual_brand_systems", description="List VBS revisions you can access for one initialized brand.")
async def list_visual_brand_systems(ctx, params: ListVisualBrandSystemsParams) -> ActionResult[VisualBrandSystemList]:
    """List the caller's VBS revisions without exposing another workspace."""
    workspace, error = await _require_vbs_workspace_owner(ctx, params.brand_id)
    if error:
        return error
    page = await ctx.store.query(VBS_SYSTEMS, where={"brand_id": params.brand_id}, order_by="-created_at", limit=200)
    records = [d for d in page.data if d.data.get("tenant_id") == workspace.data["tenant_id"]]
    if not params.include_superseded:
        records = [d for d in records if d.data.get("status") not in {"superseded", "archived"}]
    items = [
        VisualBrandSystem(id=d.id, title=f"VBS revision {d.data.get('revision', 1)}", **d.data)
        for d in records
    ]
    return ActionResult.success(VisualBrandSystemList(items=items), f"Found {len(items)} VBS revision(s).")


@chat.function(
    "activate_visual_brand_system",
    description="Approve one VBS draft revision and supersede the previously approved current revision.",
    action_type="write",
    effects=["update:visual_brand_system"],
    event="brand-strategy-hub.activate_visual_brand_system",
    data_model=VisualBrandSystem,
)
async def activate_visual_brand_system(ctx, params: ActivateVisualBrandSystemParams) -> ActionResult[VisualBrandSystem]:
    """Activate one reviewed draft and preserve its predecessor as history."""
    candidate = await ctx.store.get(VBS_SYSTEMS, params.vbs_id)
    if not candidate:
        return ActionResult.error("VBS revision not found.", retryable=False, code="VBS_NOT_FOUND")
    brand_id = candidate.data.get("brand_id", "")
    workspace, _membership, error = await _require_vbs_access(ctx, brand_id, "review")
    if error:
        return error
    if candidate.data.get("tenant_id") != workspace.data.get("tenant_id"):
        return ActionResult.error("You do not have access to this VBS revision.", retryable=False, code="VBS_ACCESS_DENIED")
    if candidate.data.get("status") != "draft" or candidate.data.get("revision") != params.expected_revision:
        return ActionResult.error(
            "This VBS revision is no longer the draft revision you reviewed.",
            retryable=True,
            code="VBS_STALE_REVISION",
        )
    if workspace.data.get("version") != params.expected_workspace_version:
        return ActionResult.error(
            "The VBS workspace changed since you opened it. Refresh and review before approving.",
            retryable=True,
            code="VBS_STALE_WORKSPACE",
        )
    integrity_error = await _require_vbs_audit_integrity(ctx, workspace)
    if integrity_error:
        return integrity_error
    advanced_workspace, error = await _advance_vbs_workspace(
        ctx, workspace, params.expected_workspace_version
    )
    if error:
        return error

    revisions = await ctx.store.query(VBS_SYSTEMS, where={"brand_id": brand_id}, order_by="-created_at", limit=200)
    current = [
        d for d in revisions.data
        if d.data.get("tenant_id") == workspace.data["tenant_id"] and d.data.get("status") == "approved_current"
    ]
    for old in current:
        await ctx.store.update(VBS_SYSTEMS, old.id, {**old.data, "status": "superseded", "superseded_at": _now_iso()})
        await _append_vbs_audit(
            ctx, brand_id=brand_id, vbs_id=old.id, event_type="vbs_superseded", details=f"Superseded by revision {params.expected_revision}."
        )
    await ctx.store.update(
        VBS_SYSTEMS,
        candidate.id,
        {**candidate.data, "status": "approved_current", "approved_at": _now_iso(), "approval_note": params.approval_note.strip()},
    )
    await _append_vbs_audit(
        ctx, brand_id=brand_id, vbs_id=candidate.id, event_type="vbs_approved_current", details=params.approval_note.strip() or "Approved as current VBS."
    )
    return ActionResult.success(
        {
            "vbs_id": candidate.id,
            "brand_id": brand_id,
            "revision": params.expected_revision,
            "status": "approved_current",
            "workspace_version": advanced_workspace.data["version"],
        },
        f"VBS revision {params.expected_revision} is now current.",
        refresh_panels=["brand_detail"],
    )


@chat.function("list_visual_brand_audit_events", description="List append-only VBS audit events for one initialized brand.")
async def list_visual_brand_audit_events(ctx, params: ListVisualBrandAuditEventsParams) -> ActionResult[AuditEventList]:
    """Read the append-only VBS audit projection owned by this caller."""
    workspace, error = await _require_vbs_workspace_owner(ctx, params.brand_id)
    if error:
        return error
    page = await ctx.store.query(VBS_AUDIT_EVENTS, where={"brand_id": params.brand_id}, order_by="-occurred_at", limit=params.limit)
    items = [
        AuditEvent(id=d.id, title=d.data.get("event_type", "audit event"), **d.data)
        for d in page.data if d.data.get("tenant_id") == workspace.data["tenant_id"]
    ]
    return ActionResult.success(AuditEventList(items=items), f"Found {len(items)} VBS audit event(s).")


@chat.function(
    "verify_visual_brand_audit_integrity",
    description="Verify integrity hashes for sealed VBS audit events in one private workspace.",
)
async def verify_visual_brand_audit_integrity(ctx, params: VerifyVisualBrandAuditIntegrityParams) -> ActionResult[AuditIntegrity]:
    """Return a read-only integrity report; this never changes audit records."""
    workspace, _membership, error = await _require_vbs_access(ctx, params.brand_id, "read")
    if error:
        return error
    result = await _verify_vbs_audit_integrity(ctx, workspace)
    return ActionResult.success(result, result.message)


@chat.function(
    "acknowledge_visual_brand_audit_incident",
    description="Record that an owner reviewed a detected VBS audit-integrity incident. This never clears the safety block or edits audit history.",
    action_type="write",
    effects=["create:visual_brand_audit_integrity_incident", "create:visual_brand_audit_event"],
    event="brand-strategy-hub.acknowledge_visual_brand_audit_incident",
    data_model=AuditIntegrityIncident,
)
async def acknowledge_visual_brand_audit_incident(ctx, params: AcknowledgeVisualBrandAuditIncidentParams) -> ActionResult[AuditIntegrityIncident]:
    """Persist an owner acknowledgement, but deliberately retain the critical-mutation block."""
    workspace, _membership, error = await _require_vbs_access(ctx, params.brand_id, "manage_access")
    if error:
        return error
    if workspace.data.get("version") != params.expected_workspace_version:
        return ActionResult.error("The VBS workspace changed. Refresh before acknowledging the integrity incident.", retryable=True, code="VBS_STALE_WORKSPACE")
    integrity = await _verify_vbs_audit_integrity(ctx, workspace)
    if integrity.valid:
        return ActionResult.error("No audit-integrity incident is currently detected for this VBS workspace.", retryable=False, code="VBS_AUDIT_INTEGRITY_HEALTHY")
    actor_id, tenant_id = _actor(ctx)
    page = await ctx.store.query(VBS_AUDIT_INCIDENTS, where={"brand_id": params.brand_id}, limit=200)
    existing = next((item for item in page.data if item.data.get("tenant_id") == tenant_id and item.data.get("invalid_event_id") == integrity.first_invalid_event_id), None)
    if existing:
        return ActionResult.success(
            AuditIntegrityIncident(id=existing.id, title="Acknowledged audit integrity incident", **existing.data),
            "This audit-integrity incident was already acknowledged. Critical changes remain paused.",
            refresh_panels=["brand_detail"],
        )
    incident = await ctx.store.create(
        VBS_AUDIT_INCIDENTS,
        {
            "brand_id": params.brand_id,
            "tenant_id": tenant_id,
            "invalid_event_id": integrity.first_invalid_event_id,
            "acknowledged_by": actor_id,
            "acknowledgement_note": params.acknowledgement_note.strip(),
            "workspace_version": workspace.data["version"],
            "created_at": _now_iso(),
        },
    )
    await _append_vbs_audit(
        ctx,
        brand_id=params.brand_id,
        vbs_id="",
        event_type="audit_integrity_incident_acknowledged",
        details=f"Owner acknowledged integrity incident for audit event {integrity.first_invalid_event_id}; critical changes remain paused.",
    )
    return ActionResult.success(
        AuditIntegrityIncident(id=incident.id, title="Acknowledged audit integrity incident", **incident.data),
        "Audit-integrity incident acknowledged. Critical changes remain paused until the mismatch is resolved outside this P0 workflow.",
        refresh_panels=["brand_detail"],
    )


@chat.function(
    "list_visual_brand_audit_incidents",
    description="List recorded VBS audit-integrity incident acknowledgements for one private workspace.",
)
async def list_visual_brand_audit_incidents(ctx, params: ListVisualBrandAuditIncidentsParams) -> ActionResult[AuditIntegrityIncidentList]:
    """Read private incident history without changing audit records or the safety gate."""
    workspace, _membership, error = await _require_vbs_access(ctx, params.brand_id, "read")
    if error:
        return error
    page = await ctx.store.query(
        VBS_AUDIT_INCIDENTS,
        where={"brand_id": params.brand_id},
        order_by="-created_at",
        limit=params.limit,
    )
    items = [
        AuditIntegrityIncident(id=item.id, title="Acknowledged audit integrity incident", **item.data)
        for item in page.data
        if item.data.get("tenant_id") == workspace.data["tenant_id"]
    ]
    return ActionResult.success(AuditIntegrityIncidentList(items=items), f"Found {len(items)} VBS audit-integrity incident acknowledgement(s).")


@chat.function(
    "create_visual_profile",
    description="Create a versioned non-personal Visual Profile draft from the current approved VBS and selected private evidence.",
    action_type="write",
    effects=["create:visual_profile"],
    event="brand-strategy-hub.create_visual_profile",
    data_model=VisualProfile,
)
async def create_visual_profile(ctx, params: CreateVisualProfileParams) -> ActionResult[VisualProfile]:
    """Create a draft profile bound deterministically to the approved VBS baseline."""
    workspace, _membership, error = await _require_vbs_access(ctx, params.brand_id, "edit")
    if error:
        return error
    if workspace.data.get("version") != params.expected_workspace_version:
        return ActionResult.error("The VBS workspace changed. Refresh before saving the profile.", retryable=True, code="VBS_STALE_WORKSPACE")
    vbs_page = await ctx.store.query(VBS_SYSTEMS, where={"brand_id": params.brand_id}, order_by="-created_at", limit=200)
    current_vbs = next((item for item in vbs_page.data if item.data.get("tenant_id") == workspace.data["tenant_id"] and item.data.get("status") == "approved_current"), None)
    if not current_vbs:
        return ActionResult.error("An approved current VBS is required before creating a Visual Profile.", retryable=False, code="VBS_CURRENT_REQUIRED")
    requested_ids = list(dict.fromkeys(params.evidence_ids))
    evidence_page = await ctx.store.query(VBS_EVIDENCE, where={"brand_id": params.brand_id}, order_by="-created_at", limit=200)
    evidence_by_id = {item.id: item for item in evidence_page.data if item.data.get("tenant_id") == workspace.data["tenant_id"]}
    missing = [item_id for item_id in requested_ids if item_id not in evidence_by_id]
    if missing:
        return ActionResult.error("One or more selected evidence references are unavailable in this private workspace.", retryable=False, code="VBS_EVIDENCE_ACCESS_DENIED")
    ineligible = [item_id for item_id in requested_ids if evidence_by_id[item_id].data.get("status") not in {"reviewed_valid", "hypothesis"}]
    if ineligible:
        return ActionResult.error(
            "A Visual Profile may include only reviewed_valid or explicitly marked hypothesis evidence.",
            retryable=False,
            code="VBS_EVIDENCE_NOT_ELIGIBLE",
        )
    advanced_workspace, error = await _advance_vbs_workspace(ctx, workspace, params.expected_workspace_version)
    if error:
        return error
    profiles = await ctx.store.query(VBS_PROFILES, where={"brand_id": params.brand_id}, order_by="-created_at", limit=200)
    owned_profiles = [item for item in profiles.data if item.data.get("tenant_id") == workspace.data["tenant_id"]]
    revision = max((int(item.data.get("revision", 0)) for item in owned_profiles), default=0) + 1
    summary, direction = params.profile_summary.strip(), params.art_direction.strip()
    snapshot_hash = _profile_snapshot_hash(current_vbs, [evidence_by_id[item_id] for item_id in requested_ids], summary, direction)
    actor_id, tenant_id = _actor(ctx)
    profile = await ctx.store.create(VBS_PROFILES, {"brand_id": params.brand_id, "revision": revision, "status": "draft", "vbs_id": current_vbs.id, "vbs_revision": current_vbs.data.get("revision", 0), "evidence_ids": requested_ids, "profile_summary": summary, "art_direction": direction, "change_note": params.change_note.strip(), "snapshot_hash": snapshot_hash, "created_by": actor_id, "tenant_id": tenant_id, "supersedes_profile_id": "", "created_at": _now_iso()})
    await _append_vbs_audit(ctx, brand_id=params.brand_id, vbs_id=current_vbs.id, event_type="visual_profile_draft_created", details=f"Created Visual Profile revision {revision}; snapshot {snapshot_hash}.")
    return ActionResult.success({"profile_id": profile.id, "brand_id": params.brand_id, "revision": revision, "status": "draft", "snapshot_hash": snapshot_hash, "workspace_version": advanced_workspace.data["version"]}, f"Created Visual Profile revision {revision}.", refresh_panels=["brand_detail"])


@chat.function("list_visual_profiles", description="List private Visual Profile revisions for one initialized VBS workspace.")
async def list_visual_profiles(ctx, params: ListVisualProfilesParams) -> ActionResult[VisualProfileList]:
    """List only the caller's profile revisions, optionally excluding history."""
    workspace, error = await _require_vbs_workspace_owner(ctx, params.brand_id)
    if error:
        return error
    page = await ctx.store.query(VBS_PROFILES, where={"brand_id": params.brand_id}, order_by="-created_at", limit=200)
    records = [item for item in page.data if item.data.get("tenant_id") == workspace.data["tenant_id"]]
    if not params.include_superseded:
        records = [item for item in records if item.data.get("status") not in {"superseded", "archived"}]
    return ActionResult.success(VisualProfileList(items=[VisualProfile(id=item.id, title=f"Visual Profile revision {item.data.get('revision', 1)}", **item.data) for item in records]), f"Found {len(records)} Visual Profile revision(s).")


@chat.function(
    "activate_visual_profile",
    description="Approve one Visual Profile draft as current and supersede the prior current profile.",
    action_type="write",
    effects=["update:visual_profile"],
    event="brand-strategy-hub.activate_visual_profile",
    data_model=VisualProfile,
)
async def activate_visual_profile(ctx, params: ActivateVisualProfileParams) -> ActionResult[VisualProfile]:
    """Approve one profile revision and preserve any previous current revision."""
    candidate = await ctx.store.get(VBS_PROFILES, params.profile_id)
    if not candidate:
        return ActionResult.error("Visual Profile revision not found.", retryable=False, code="VISUAL_PROFILE_NOT_FOUND")
    brand_id = candidate.data.get("brand_id", "")
    workspace, _membership, error = await _require_vbs_access(ctx, brand_id, "review")
    if error:
        return error
    if candidate.data.get("tenant_id") != workspace.data["tenant_id"]:
        return ActionResult.error("You do not have access to this Visual Profile revision.", retryable=False, code="VBS_ACCESS_DENIED")
    if candidate.data.get("status") != "draft" or candidate.data.get("revision") != params.expected_revision:
        return ActionResult.error("This Visual Profile revision is no longer the draft you reviewed.", retryable=True, code="VISUAL_PROFILE_STALE")
    if workspace.data.get("version") != params.expected_workspace_version:
        return ActionResult.error("The VBS workspace changed. Refresh before approving the profile.", retryable=True, code="VBS_STALE_WORKSPACE")
    integrity_error = await _require_vbs_audit_integrity(ctx, workspace)
    if integrity_error:
        return integrity_error
    bound_vbs = await ctx.store.get(VBS_SYSTEMS, candidate.data.get("vbs_id", ""))
    if (
        not bound_vbs
        or bound_vbs.data.get("tenant_id") != workspace.data["tenant_id"]
        or bound_vbs.data.get("status") != "approved_current"
    ):
        return ActionResult.error(
            "This Visual Profile is based on a superseded VBS baseline. Create a new profile from the current VBS.",
            retryable=False,
            code="VISUAL_PROFILE_BASELINE_STALE",
        )
    evidence_ids = candidate.data.get("evidence_ids", [])
    if evidence_ids:
        evidence_page = await ctx.store.query(VBS_EVIDENCE, where={"brand_id": brand_id}, order_by="-created_at", limit=200)
        current_evidence = {item.id: item for item in evidence_page.data if item.data.get("tenant_id") == workspace.data["tenant_id"]}
        if any(item_id not in current_evidence or current_evidence[item_id].data.get("status") not in {"reviewed_valid", "hypothesis"} for item_id in evidence_ids):
            return ActionResult.error(
                "This Visual Profile includes evidence that is no longer eligible. Create a new profile snapshot.",
                retryable=False,
                code="VISUAL_PROFILE_EVIDENCE_STALE",
            )
    advanced_workspace, error = await _advance_vbs_workspace(ctx, workspace, params.expected_workspace_version)
    if error:
        return error
    profiles = await ctx.store.query(VBS_PROFILES, where={"brand_id": brand_id}, order_by="-created_at", limit=200)
    for prior in profiles.data:
        if prior.data.get("tenant_id") == workspace.data["tenant_id"] and prior.data.get("status") == "approved_current":
            await ctx.store.update(VBS_PROFILES, prior.id, {**prior.data, "status": "superseded", "superseded_at": _now_iso(), "superseded_by": candidate.id})
    await ctx.store.update(VBS_PROFILES, candidate.id, {**candidate.data, "status": "approved_current", "approved_at": _now_iso(), "approval_note": params.approval_note.strip()})
    await _append_vbs_audit(ctx, brand_id=brand_id, vbs_id=candidate.data.get("vbs_id", ""), event_type="visual_profile_approved_current", details=params.approval_note.strip() or f"Approved Visual Profile revision {params.expected_revision}.")
    return ActionResult.success({"profile_id": candidate.id, "brand_id": brand_id, "revision": params.expected_revision, "status": "approved_current", "snapshot_hash": candidate.data.get("snapshot_hash", ""), "workspace_version": advanced_workspace.data["version"]}, f"Visual Profile revision {params.expected_revision} is now current.", refresh_panels=["brand_detail"])


@chat.function("resolve_current_visual_profile", description="Resolve the one deterministic approved VBS plus approved Visual Profile baseline; fails closed when incomplete or stale.")
async def resolve_current_visual_profile(ctx, params: ResolveCurrentVisualProfileParams) -> ActionResult[VisualProfile]:
    """Resolve only a complete, current approved baseline; never guess a fallback."""
    workspace, error = await _require_vbs_workspace_owner(ctx, params.brand_id)
    if error:
        return error
    profiles = await ctx.store.query(VBS_PROFILES, where={"brand_id": params.brand_id}, order_by="-created_at", limit=200)
    current = next((item for item in profiles.data if item.data.get("tenant_id") == workspace.data["tenant_id"] and item.data.get("status") == "approved_current"), None)
    if not current:
        return ActionResult.error("No approved current Visual Profile exists for this workspace.", retryable=False, code="VISUAL_PROFILE_CURRENT_REQUIRED")
    vbs = await ctx.store.get(VBS_SYSTEMS, current.data.get("vbs_id", ""))
    if not vbs or vbs.data.get("tenant_id") != workspace.data["tenant_id"] or vbs.data.get("status") != "approved_current":
        return ActionResult.error("The current Visual Profile is not bound to an approved current VBS. Resolution is blocked.", retryable=False, code="VISUAL_PROFILE_BASELINE_STALE")
    return ActionResult.success(VisualProfile(id=current.id, title=f"Visual Profile revision {current.data.get('revision', 1)}", **current.data), "Resolved approved Visual Profile baseline.")


@chat.function(
    "register_visual_evidence",
    description=(
        "Register a private, unreviewed HTTPS reference for a VBS decision. "
        "P0 stores the reference only and never fetches the URL."
    ),
    action_type="write",
    effects=["create:visual_evidence"],
    event="brand-strategy-hub.register_visual_evidence",
    data_model=VisualEvidence,
)
async def register_visual_evidence(ctx, params: RegisterVisualEvidenceParams) -> ActionResult[VisualEvidence]:
    """Register a non-fetched evidence reference within the caller's VBS workspace."""
    workspace, _membership, error = await _require_vbs_access(ctx, params.brand_id, "edit")
    if error:
        return error
    canonical_url, validation_error = _validate_public_https_reference(params.source_url)
    if validation_error:
        return ActionResult.error(validation_error, retryable=False, code="VBS_EVIDENCE_URL_REJECTED")
    if workspace.data.get("version") != params.expected_workspace_version:
        return ActionResult.error(
            "The VBS workspace changed since you opened it. Refresh and review before saving evidence.",
            retryable=True,
            code="VBS_STALE_WORKSPACE",
        )
    advanced_workspace, error = await _advance_vbs_workspace(
        ctx, workspace, params.expected_workspace_version
    )
    if error:
        return error
    actor_id, tenant_id = _actor(ctx)
    evidence = await ctx.store.create(
        VBS_EVIDENCE,
        {
            "brand_id": params.brand_id,
            "source_url": canonical_url,
            "source_title": params.source_title.strip(),
            "observation": params.observation.strip(),
            "status": "discovered",
            "workspace_version": advanced_workspace.data["version"],
            "created_by": actor_id,
            "tenant_id": tenant_id,
            "created_at": _now_iso(),
        },
    )
    await _append_vbs_audit(
        ctx,
        brand_id=params.brand_id,
        vbs_id="",
        event_type="evidence_registered",
        details=f"Registered unreviewed reference: {canonical_url}",
    )
    return ActionResult.success(
        {
            "id": evidence.id,
            "brand_id": params.brand_id,
            "source_url": canonical_url,
            "status": "discovered",
            "workspace_version": advanced_workspace.data["version"],
        },
        "Unreviewed evidence reference registered. The URL was not fetched.",
        refresh_panels=["brand_detail"],
    )


@chat.function(
    "review_visual_evidence",
    description="Review one private VBS evidence reference as valid, hypothesis, rejected, or archived.",
    action_type="write",
    effects=["update:visual_evidence"],
    event="brand-strategy-hub.review_visual_evidence",
    data_model=VisualEvidence,
)
async def review_visual_evidence(ctx, params: ReviewVisualEvidenceParams) -> ActionResult[VisualEvidence]:
    """Apply one allowed P0 evidence review transition and append its audit record."""
    evidence = await ctx.store.get(VBS_EVIDENCE, params.evidence_id)
    if not evidence:
        return ActionResult.error("Evidence reference not found.", retryable=False, code="VBS_EVIDENCE_NOT_FOUND")
    brand_id = evidence.data.get("brand_id", "")
    workspace, _membership, error = await _require_vbs_access(ctx, brand_id, "review")
    if error:
        return error
    if evidence.data.get("tenant_id") != workspace.data["tenant_id"]:
        return ActionResult.error("You do not have access to this evidence reference.", retryable=False, code="VBS_ACCESS_DENIED")
    current_status = evidence.data.get("status", "discovered")
    if current_status != params.expected_status:
        return ActionResult.error("This evidence reference changed since you opened it. Refresh before reviewing.", retryable=True, code="VBS_EVIDENCE_STALE")
    allowed = {
        "discovered": {"reviewed_valid", "hypothesis", "rejected", "archived"},
        "reviewed_valid": {"archived"},
        "hypothesis": {"reviewed_valid", "rejected", "archived"},
        "rejected": {"archived"},
        "archived": set(),
    }
    if params.decision not in allowed.get(current_status, set()):
        return ActionResult.error(
            f"Evidence cannot transition from '{current_status}' to '{params.decision}'.",
            retryable=False,
            code="VBS_EVIDENCE_INVALID_TRANSITION",
        )
    if workspace.data.get("version") != params.expected_workspace_version:
        return ActionResult.error("The VBS workspace changed. Refresh before reviewing evidence.", retryable=True, code="VBS_STALE_WORKSPACE")
    integrity_error = await _require_vbs_audit_integrity(ctx, workspace)
    if integrity_error:
        return integrity_error
    advanced_workspace, error = await _advance_vbs_workspace(ctx, workspace, params.expected_workspace_version)
    if error:
        return error
    actor_id, _ = _actor(ctx)
    updated = await ctx.store.update(
        VBS_EVIDENCE,
        evidence.id,
        {
            **evidence.data,
            "status": params.decision,
            "review_note": params.review_note.strip(),
            "reviewed_by": actor_id,
            "reviewed_at": _now_iso(),
            "workspace_version": advanced_workspace.data["version"],
        },
    )
    await _append_vbs_audit(
        ctx,
        brand_id=brand_id,
        vbs_id="",
        event_type=f"evidence_{params.decision}",
        details=params.review_note.strip(),
    )
    return ActionResult.success(
        VisualEvidence(id=updated.id, title=updated.data.get("source_title") or updated.data.get("source_url", updated.id), **updated.data),
        f"Evidence marked as {params.decision}.",
        refresh_panels=["brand_detail"],
    )


@chat.function("list_visual_evidence", description="List private VBS evidence references for one initialized brand.")
async def list_visual_evidence(ctx, params: ListVisualEvidenceParams) -> ActionResult[VisualEvidenceList]:
    """List only evidence records owned by the caller's tenant and workspace."""
    workspace, error = await _require_vbs_workspace_owner(ctx, params.brand_id)
    if error:
        return error
    page = await ctx.store.query(
        VBS_EVIDENCE, where={"brand_id": params.brand_id}, order_by="-created_at", limit=params.limit
    )
    items = [
        VisualEvidence(id=d.id, title=d.data.get("source_title") or d.data.get("source_url", d.id), **d.data)
        for d in page.data if d.data.get("tenant_id") == workspace.data["tenant_id"]
    ]
    return ActionResult.success(VisualEvidenceList(items=items), f"Found {len(items)} VBS evidence reference(s).")


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
    if params.site_id:
        existing_page = await ctx.store.query("brand_profiles", where={"site_id": params.site_id}, limit=1)
        if existing_page.data:
            existing = existing_page.data[0]
            return ActionResult.error(
                f"A brand profile already exists for site_id '{params.site_id}' "
                f"(brand '{existing.data.get('brand_name', existing.id)}', id {existing.id}). "
                "Use update_brand_profile on that one instead of creating a duplicate.",
                retryable=False, code="DUPLICATE_SITE_ID",
            )
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
            "content_topics": params.content_topics,
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
    if params.content_topics is not None:
        updates["content_topics"] = params.content_topics

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
    "add_brand_competitor",
    description="Track a named competitor against a brand, with observed strengths and weaknesses.",
    action_type="write",
    chain_callable=True,
    effects=["create:competitor_profile"],
    event="created",
    data_model=CompetitorProfile,
)
async def add_brand_competitor(ctx, params: AddCompetitorParams) -> ActionResult:
    """Add one competitor profile linked to a brand."""
    brand_doc = await ctx.store.get("brand_profiles", params.brand_id)
    if not brand_doc:
        return ActionResult.error(f"Brand profile '{params.brand_id}' not found.", retryable=False)

    dup_page = await ctx.store.query("competitor_profiles", where={"brand_id": params.brand_id}, limit=500)
    for d in dup_page.data:
        if d.data.get("name", "").strip().lower() == params.name.strip().lower():
            return ActionResult.error(
                f"Competitor '{params.name}' is already tracked for this brand (id {d.id}). "
                "Update that record instead of adding a duplicate — duplicate competitors "
                "double-count in SWOT's opportunities/threats.",
                retryable=False, code="DUPLICATE_COMPETITOR",
            )

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
    "list_brand_competitors",
    description="List tracked competitors, optionally filtered by brand.",
    action_type="read",
    data_model=CompetitorProfileList,
)
async def list_brand_competitors(ctx, params: ListCompetitorsParams) -> ActionResult:
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

    dup_page = await ctx.store.query("target_segments", where={"brand_id": params.brand_id}, limit=500)
    for d in dup_page.data:
        if d.data.get("segment_name", "").strip().lower() == params.segment_name.strip().lower():
            return ActionResult.error(
                f"Segment '{params.segment_name}' already exists for this brand (id {d.id}). "
                "Use that segment for gap analysis instead of creating a duplicate.",
                retryable=False, code="DUPLICATE_SEGMENT",
            )

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
        "add_brand_competitor for a sharper result."
    ),
    action_type="write",
    chain_callable=True,
    effects=["create:swot_result"],
    event="created",
    data_model=SWOTResult,
)
async def run_swot_analysis(ctx, params: RunSWOTAnalysisParams) -> ActionResult:
    """Derive and store a SWOT snapshot for a brand, superseding any
    previous current snapshot so exactly one stays marked current."""
    brand_doc = await ctx.store.get("brand_profiles", params.brand_id)
    if not brand_doc:
        return ActionResult.error(f"Brand profile '{params.brand_id}' not found.", retryable=False)

    brand = brand_doc.data
    if not any([
        brand.get("mission"), brand.get("vision"), brand.get("value_proposition"),
        brand.get("tone_of_voice"), brand.get("unique_selling_points"),
    ]):
        return ActionResult.error(
            f"Brand profile '{params.brand_id}' has no mission, vision, value "
            "proposition, tone of voice, or USPs set — a SWOT built on an "
            "empty profile is just noise. Fill in the brand profile "
            "(update_brand_profile) before running SWOT.",
            retryable=False, code="EMPTY_BRAND_PROFILE",
        )

    comp_page = await ctx.store.query("competitor_profiles", where={"brand_id": params.brand_id}, limit=500)
    competitors = [d.data for d in comp_page.data]

    strengths, weaknesses, opportunities, threats = build_swot(brand_doc.data, competitors)

    # Supersede the previous current snapshot(s) for this brand -- exactly
    # one SWOT stays "current" at a time, so a reader never has to guess
    # which of several results reflects reality now.
    prev_page = await ctx.store.query("swot_results", where={"brand_id": params.brand_id}, limit=500)
    prev_current = [d for d in prev_page.data if d.data.get("is_current", True)]
    superseded_at = _now_iso()
    for prev in prev_current:
        await ctx.store.update("swot_results", prev.id, {"is_current": False, "superseded_at": superseded_at})

    doc = await ctx.store.create(
        "swot_results",
        {
            "brand_id": params.brand_id,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "opportunities": opportunities,
            "threats": threats,
            "is_current": True,
            "superseded_at": "",
        },
    )
    return ActionResult.success(
        _to_swot_result(doc), summary=(
            f"SWOT analysis run for brand {params.brand_id}."
            + (f" Superseded {len(prev_page.data)} previous snapshot(s)." if prev_page.data else "")
        ),
        refresh_panels=["brand_detail"],
    )


@chat.function(
    "list_swot_results",
    description="List past SWOT analysis snapshots, optionally filtered by brand.",
    action_type="read",
    data_model=SWOTResultList,
)
async def list_swot_results(ctx, params: ListSWOTResultsParams) -> ActionResult:
    """List SWOT results, optionally filtered by brand. Defaults to only the
    CURRENT snapshot per brand -- pass include_superseded=true for history."""
    page = await ctx.store.query("swot_results", order_by="-created_at", limit=500)
    items = list(page.data)
    if params.brand_id:
        items = [d for d in items if d.data.get("brand_id") == params.brand_id]
    if not params.include_superseded:
        items = [d for d in items if d.data.get("is_current", True)]
    items = items[: params.limit]
    entities = [_to_swot_result(d) for d in items]
    current_note = "" if params.include_superseded else " (current only)"
    return ActionResult.success(SWOTResultList(items=entities, total=len(entities)), summary=f"{len(entities)} SWOT result(s){current_note}.")


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
    """Derive and store a brand-vs-audience gap analysis, superseding any
    previous current result for the same (brand, segment) pair."""
    brand_doc = await ctx.store.get("brand_profiles", params.brand_id)
    if not brand_doc:
        return ActionResult.error(f"Brand profile '{params.brand_id}' not found.", retryable=False)
    segment_doc = await ctx.store.get("target_segments", params.segment_id)
    if not segment_doc:
        return ActionResult.error(f"Target segment '{params.segment_id}' not found.", retryable=False)
    if segment_doc.data.get("brand_id") != params.brand_id:
        return ActionResult.error(
            f"Target segment '{params.segment_id}' belongs to a different brand "
            f"than '{params.brand_id}' — a gap analysis needs a segment that "
            "actually belongs to the brand being analysed.",
            retryable=False, code="SEGMENT_BRAND_MISMATCH",
        )

    gaps, recommendations = build_gap_analysis(brand_doc.data, segment_doc.data)

    # Supersede the previous current result for this exact (brand, segment)
    # pair -- same "one current, rest archived" rule as SWOT.
    prev_page = await ctx.store.query(
        "gap_analysis_results", where={"brand_id": params.brand_id, "segment_id": params.segment_id}, limit=500,
    )
    prev_current = [d for d in prev_page.data if d.data.get("is_current", True)]
    superseded_at = _now_iso()
    for prev in prev_current:
        await ctx.store.update("gap_analysis_results", prev.id, {"is_current": False, "superseded_at": superseded_at})

    doc = await ctx.store.create(
        "gap_analysis_results",
        {
            "brand_id": params.brand_id,
            "segment_id": params.segment_id,
            "gaps": gaps,
            "recommendations": recommendations,
            "is_current": True,
            "superseded_at": "",
        },
    )
    return ActionResult.success(
        _to_gap_analysis_result(doc), summary="Gap analysis run — superseded any prior result for this segment.",
        refresh_panels=["brand_detail"],
    )


@chat.function(
    "list_gap_analyses",
    description="List past brand-vs-audience gap analysis results, optionally filtered by brand.",
    action_type="read",
    data_model=GapAnalysisResultList,
)
async def list_gap_analyses(ctx, params: ListGapAnalysesParams) -> ActionResult:
    """List gap analysis results, optionally filtered by brand. Defaults to
    only the CURRENT result per (brand, segment) pair -- pass
    include_superseded=true for history."""
    page = await ctx.store.query("gap_analysis_results", order_by="-created_at", limit=500)
    items = list(page.data)
    if params.brand_id:
        items = [d for d in items if d.data.get("brand_id") == params.brand_id]
    if not params.include_superseded:
        items = [d for d in items if d.data.get("is_current", True)]
    items = items[: params.limit]
    entities = [_to_gap_analysis_result(d) for d in items]
    current_note = "" if params.include_superseded else " (current only)"
    return ActionResult.success(GapAnalysisResultList(items=entities, total=len(entities)), summary=f"{len(entities)} gap analysis result(s){current_note}.")


# ──────────────────────────────────────────────────────────────────────────
# Deletion / archival — every collection here anchors off brand_id, so
# deleting a brand cascades; deleting a competitor/segment is a plain leaf
# delete; SWOT/gap-analysis snapshots are archived (superseded), not deleted,
# so the "actual vs outdated" history stays inspectable.
# ──────────────────────────────────────────────────────────────────────────

@chat.function(
    "delete_brand_competitor",
    description="Permanently delete one tracked competitor. Does not affect past SWOT snapshots already derived from it.",
    action_type="destructive",
    chain_callable=True,
    effects=["delete:competitor_profile"],
    event="deleted",
    data_model=DeleteResult,
)
async def delete_brand_competitor(ctx, params: DeleteCompetitorParams) -> ActionResult:
    """Delete one competitor profile."""
    doc = await ctx.store.get("competitor_profiles", params.competitor_id)
    if not doc:
        return ActionResult.error(f"Competitor '{params.competitor_id}' not found.", retryable=False)
    await ctx.store.delete("competitor_profiles", params.competitor_id)
    return ActionResult.success(
        DeleteResult(id=params.competitor_id, title="Competitor deleted", deleted=True),
        summary=f"Competitor '{doc.data.get('name', params.competitor_id)}' deleted.",
        refresh_panels=["brand_detail"],
    )


@chat.function(
    "delete_target_segment",
    description="Permanently delete one target audience segment. Does not affect past gap-analysis results already derived from it.",
    action_type="destructive",
    chain_callable=True,
    effects=["delete:target_segment"],
    event="deleted",
    data_model=DeleteResult,
)
async def delete_target_segment(ctx, params: DeleteTargetSegmentParams) -> ActionResult:
    """Delete one target segment."""
    doc = await ctx.store.get("target_segments", params.segment_id)
    if not doc:
        return ActionResult.error(f"Target segment '{params.segment_id}' not found.", retryable=False)
    await ctx.store.delete("target_segments", params.segment_id)
    return ActionResult.success(
        DeleteResult(id=params.segment_id, title="Target segment deleted", deleted=True),
        summary=f"Segment '{doc.data.get('segment_name', params.segment_id)}' deleted.",
        refresh_panels=["brand_detail"],
    )


@chat.function(
    "delete_brand_profile",
    description=(
        "Permanently delete a brand profile AND cascade-delete everything "
        "anchored to it: its tracked competitors, target segments, SWOT "
        "snapshots (current + superseded), and gap analyses. Requires "
        "confirm_cascade=true. Irreversible."
    ),
    action_type="destructive",
    chain_callable=True,
    effects=["delete:brand_profile", "delete:competitor_profile", "delete:target_segment", "delete:swot_result", "delete:gap_analysis_result"],
    event="deleted",
    data_model=DeleteResult,
)
async def delete_brand_profile(ctx, params: DeleteBrandProfileParams) -> ActionResult:
    """Delete a brand profile and cascade-delete its dependents."""
    doc = await ctx.store.get("brand_profiles", params.brand_id)
    if not doc:
        return ActionResult.error(f"Brand profile '{params.brand_id}' not found.", retryable=False)
    if not params.confirm_cascade:
        return ActionResult.error(
            "Deleting a brand profile cascades to ALL of its competitors, "
            "target segments, SWOT snapshots, and gap analyses. Pass "
            "confirm_cascade=true to proceed.",
            retryable=False, code="CONFIRM_CASCADE_REQUIRED",
        )

    for collection in ("competitor_profiles", "target_segments", "swot_results", "gap_analysis_results"):
        page = await ctx.store.query(collection, where={"brand_id": params.brand_id}, limit=500)
        for d in page.data:
            await ctx.store.delete(collection, d.id)

    await ctx.store.delete("brand_profiles", params.brand_id)
    return ActionResult.success(
        DeleteResult(id=params.brand_id, title="Brand profile deleted", deleted=True),
        summary=f"Brand profile '{doc.data.get('brand_name', params.brand_id)}' and all its dependents deleted.",
        refresh_panels=["brands", "brand_detail"],
    )


@chat.function(
    "archive_swot_result",
    description="Mark one SWOT snapshot as superseded (outdated) without deleting it, so its history stays inspectable but it stops showing as current.",
    action_type="write",
    chain_callable=True,
    effects=["update:swot_result"],
    event="updated",
    data_model=SWOTResult,
)
async def archive_swot_result(ctx, params: ArchiveSWOTResultParams) -> ActionResult:
    """Manually mark one SWOT snapshot as superseded."""
    doc = await ctx.store.get("swot_results", params.swot_id)
    if not doc:
        return ActionResult.error(f"SWOT result '{params.swot_id}' not found.", retryable=False)
    updated = await ctx.store.update(
        "swot_results", params.swot_id, {"is_current": False, "superseded_at": _now_iso()}
    )
    return ActionResult.success(
        _to_swot_result(updated), summary="SWOT snapshot marked as superseded.",
        refresh_panels=["brand_detail"],
    )


@chat.function(
    "archive_gap_analysis",
    description="Mark one gap analysis as superseded (outdated) without deleting it, so its history stays inspectable but it stops showing as current.",
    action_type="write",
    chain_callable=True,
    effects=["update:gap_analysis_result"],
    event="updated",
    data_model=GapAnalysisResult,
)
async def archive_gap_analysis(ctx, params: ArchiveGapAnalysisParams) -> ActionResult:
    """Manually mark one gap analysis as superseded."""
    doc = await ctx.store.get("gap_analysis_results", params.gap_analysis_id)
    if not doc:
        return ActionResult.error(f"Gap analysis '{params.gap_analysis_id}' not found.", retryable=False)
    updated = await ctx.store.update(
        "gap_analysis_results", params.gap_analysis_id, {"is_current": False, "superseded_at": _now_iso()}
    )
    return ActionResult.success(
        _to_gap_analysis_result(updated), summary="Gap analysis marked as superseded.",
        refresh_panels=["brand_detail"],
    )


@chat.function(
    "purge_brand_strategy_data",
    description=(
        "Wipe ALL brand strategy WORKING data derived from a brand -- "
        "tracked competitors, target segments, SWOT snapshots (current + "
        "superseded), and gap analyses. Brand profiles themselves are NEVER "
        "touched, mirroring Content Strategy Hub's purge_pipeline_data "
        "(which keeps site profiles): a brand profile is the anchor "
        "record, equivalent to a connected site, not disposable pipeline "
        "output. Requires confirm_wipe=true."
    ),
    action_type="destructive",
    chain_callable=True,
    effects=["delete:competitor_profile", "delete:target_segment", "delete:swot_result", "delete:gap_analysis_result"],
    event="brand_strategy_purged",
    data_model=PurgeResult,
)
async def purge_brand_strategy_data(ctx, params: PurgeBrandStrategyDataParams) -> ActionResult:
    """Delete every competitor/segment/SWOT/gap-analysis record, keeping brand profiles."""
    if not params.confirm_wipe:
        return ActionResult.error(
            "This permanently deletes ALL tracked competitors, target "
            "segments, SWOT snapshots, and gap analyses for every brand. "
            "Brand profiles themselves are kept. Pass confirm_wipe=true to proceed.",
            retryable=False, code="CONFIRM_WIPE_REQUIRED",
        )

    counts = {}
    for collection in ("competitor_profiles", "target_segments", "swot_results", "gap_analysis_results"):
        page = await ctx.store.query(collection, limit=1000)
        counts[collection] = len(page.data)
        for d in page.data:
            await ctx.store.delete(collection, d.id)

    brand_page = await ctx.store.query("brand_profiles", limit=1000)
    kept_brand_ids = [d.id for d in brand_page.data]

    return ActionResult.success(
        PurgeResult(
            id="purge",
            title="Brand strategy data purge",
            competitors_removed=counts.get("competitor_profiles", 0),
            segments_removed=counts.get("target_segments", 0),
            swot_results_removed=counts.get("swot_results", 0),
            gap_analyses_removed=counts.get("gap_analysis_results", 0),
            kept_brand_ids=kept_brand_ids,
        ),
        summary=(
            f"Purged {counts.get('competitor_profiles', 0)} competitor(s), "
            f"{counts.get('target_segments', 0)} segment(s), "
            f"{counts.get('swot_results', 0)} SWOT result(s), "
            f"{counts.get('gap_analysis_results', 0)} gap analysis(es). "
            f"Kept {len(kept_brand_ids)} brand profile(s)."
        ),
        refresh_panels=["brands", "brand_detail"],
    )


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

    brand = brand_doc.data
    if not any([
        brand.get("mission"), brand.get("value_proposition"),
        brand.get("tone_of_voice"), brand.get("unique_selling_points"),
    ]):
        return ActionResult.error(
            f"Brand profile '{params.brand_id}' has no mission, value proposition, "
            "tone of voice, or USPs set. Handing this off to Content Strategy Hub now "
            "would create a site profile with no real positioning -- fill in the "
            "brand profile (update_brand_profile) first.",
            retryable=False, code="EMPTY_BRAND_PROFILE",
        )

    swot_page = await ctx.store.query("swot_results", where={"brand_id": params.brand_id}, limit=500)
    current_swot = [d for d in swot_page.data if d.data.get("is_current", True)]
    if not current_swot:
        return ActionResult.error(
            f"Brand profile '{params.brand_id}' has no current SWOT analysis yet. "
            "Run run_swot_analysis first so downstream content strategy is grounded "
            "in an actual strengths/weaknesses/opportunities/threats read, not just "
            "raw profile fields.",
            retryable=False, code="SWOT_REQUIRED",
        )

    handoff = _to_content_handoff(
        brand_doc.data, params.brand_id, params.site_id, params.domain, params.target_languages
    )
    return ActionResult.success(handoff, summary=f"Content strategy handoff ready for site '{params.site_id}'.")


_SITES_CACHE_MARKER = "quick_add_sites"  # value of the "kind" field identifying the one cache row


async def _cache_connected_sites(ctx, sites: list[dict], problems: list[dict]) -> None:
    """Persist the last-known-good Quick Add source list to this app's own
    store. Needed because a real-user chat/tool call to list_connected_sites
    reaches the target extension with a normal, populated user context, while
    the SAME ctx.extensions.call made from inside a *panel render* has been
    observed to reach it with an empty user context (kernel-side — a
    ContextFactory.create_child gap during panel rendering, not something
    fixable from an extension's own code). Caching what the working call path
    already proved lets the panel show real data without depending on the
    panel-render call path at all.

    Looked up by a "kind" marker via query(where=...), NOT a fixed doc id:
    store.create always server-assigns its own id (a caller-supplied id is
    not honoured), so a fixed-id get() would never find the row it wrote.
    """
    payload = {"kind": _SITES_CACHE_MARKER, "sites": sites, "problems": problems}
    page = await ctx.store.query("connected_sites_cache", where={"kind": _SITES_CACHE_MARKER}, limit=1)
    if page.data:
        await ctx.store.update("connected_sites_cache", page.data[0].id, payload)
    else:
        await ctx.store.create("connected_sites_cache", payload)


async def _read_cached_connected_sites(ctx) -> tuple[list[dict], list[dict], bool]:
    """Read the cached Quick Add source list. Returns (sites, problems, has_cache)."""
    page = await ctx.store.query("connected_sites_cache", where={"kind": _SITES_CACHE_MARKER}, limit=1)
    if not page.data:
        return [], [], False
    doc = page.data[0]
    return doc.data.get("sites", []), doc.data.get("problems", []), True


@chat.function(
    "list_connected_sites",
    description=(
        "List the sites already connected in other apps (WordPress Hub today, "
        "any future site provider) that Quick Add offers as one-click brand "
        "candidates, flagging which ones already have a brand profile here. "
        "Also the diagnostic for an empty Quick Add list: it reports whether "
        "a provider could not be reached and why."
    ),
    action_type="read",
    data_model=ConnectedSiteList,
)
async def list_connected_sites(ctx, params: ListConnectedSitesParams) -> ActionResult:
    """Read connected sites from every registered site-provider extension,
    and cache the result so the panel can show it reliably (see
    _cache_connected_sites)."""
    sites, problems = await fetch_connected_sites(ctx)
    await _cache_connected_sites(ctx, sites, problems)

    page = await ctx.store.query("brand_profiles", limit=500)
    existing_site_ids = {
        d.data.get("site_id") for d in page.data if d.data.get("site_id")
    }

    items = [
        ConnectedSite(
            id=s.get("site_id", ""),
            title=s.get("name") or s.get("site_id", ""),
            kind="connected_site",
            site_id=s.get("site_id", ""),
            url=s.get("url", ""),
            status=s.get("status", ""),
            provider=s.get("provider", ""),
            already_tracked=s.get("site_id") in existing_site_ids,
        )
        for s in sites[: max(1, min(params.limit, 100))]
    ]

    if problems:
        detail = "; ".join(f"{p['provider']}: {p['reason']}" for p in problems)
        return ActionResult.success(
            ConnectedSiteList(items=items),
            summary=(
                f"{len(items)} connected site(s) readable. "
                f"Could not read from — {detail}"
            ),
            refresh_panels=["brands"],
        )

    fresh = sum(1 for i in items if not i.already_tracked)
    return ActionResult.success(
        ConnectedSiteList(items=items),
        summary=f"{len(items)} connected site(s), {fresh} without a brand profile yet.",
        refresh_panels=["brands"],
    )


# ──────────────────────────────────────────────────────────────────────────
# Panels
# ──────────────────────────────────────────────────────────────────────────

def _quick_add_block(connected_sites: list[dict], existing_site_ids: set[str],
                     problems: list[dict] | None = None, has_cache: bool = True) -> object:
    """Quick Add: one real button per connected site not yet tracked as a
    brand here, pre-filling create_brand_profile's site_id/brand_name via
    ui.Call so a brand can be started in one click straight from whatever
    is already connected in WordPress Hub (or any future site provider in
    SITE_PROVIDER_APP_IDS) -- no retyping the domain, no chat message.

    ALWAYS returns a card, never None: if there is nothing to offer, the card
    says WHY (no provider reachable / nothing connected / all already added /
    not loaded yet) and carries a Refresh button that runs the REAL read
    (list_connected_sites) and re-renders. A silently missing card is
    unfixable from the UI, which is exactly the failure mode this replaces.
    """
    problems = problems or []
    candidates = [s for s in connected_sites if s.get("site_id") not in existing_site_ids]

    refresh = ui.Button(
        "Refresh", variant="secondary", size="sm", icon="RefreshCw",
        on_click=ui.Call("list_connected_sites"),
    )

    if not has_cache and not connected_sites and not problems:
        return ui.Card(
            title="Quick Add — from connected sites",
            content=ui.Stack(direction="v", gap=2, children=[
                ui.Text(
                    "Not loaded yet — click Refresh to pull sites connected "
                    "in WordPress Hub (or any future site provider).",
                    variant="caption",
                ),
                refresh,
            ]),
        )

    if candidates:
        body: list = [
            ui.Text(
                f"{len(candidates)} connected site(s) not tracked as a brand yet — "
                "click one to create its brand profile.",
                variant="caption",
            ),
            ui.Stack(direction="h", gap=1, wrap=True, children=[
                ui.Button(
                    s.get("name") or s["site_id"],
                    variant="secondary", size="sm", icon="Plus",
                    on_click=ui.Call(
                        "create_brand_profile",
                        brand_name=s.get("name") or s["site_id"],
                        site_id=s["site_id"],
                    ),
                )
                for s in candidates
            ]),
        ]
    elif problems:
        body = [
            ui.Text(
                "Could not read connected sites from: "
                + ", ".join(p["provider"] for p in problems),
                variant="body",
            ),
            ui.Text(problems[0]["reason"], variant="caption"),
        ]
    elif connected_sites:
        body = [ui.Text(
            "Every connected site already has a brand profile.",
            variant="caption",
        )]
    else:
        body = [ui.Text(
            "No sites connected yet — connect one in WordPress Hub and it "
            "will appear here.",
            variant="caption",
        )]

    return ui.Card(
        title="Quick Add — from connected sites",
        content=ui.Stack(direction="v", gap=2, children=body + [refresh]),
    )


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
    """Sidebar list of tracked brand profiles -> opens the detail overlay.
    Always carries its own 'New brand' ui.Form so the very first brand
    (and every one after) can be created directly from the panel --
    no chat message required. Also offers Quick Add buttons for any site
    already connected elsewhere (WordPress Hub today, more providers later
    via SITE_PROVIDER_APP_IDS)."""
    page = await ctx.store.query("brand_profiles", order_by="-created_at", limit=200)
    docs = list(page.data)
    existing_site_ids = {d.data.get("site_id") for d in docs if d.data.get("site_id")}
    # Read from cache, NOT a live ctx.extensions.call here: a panel render
    # runs in a context where inter-extension IPC has been observed to fail
    # (empty user context downstream), while the same call from a real
    # chat/tool invocation (list_connected_sites itself) works and refreshes
    # this cache. See _cache_connected_sites for the full explanation.
    connected_sites, site_problems, has_cache = await _read_cached_connected_sites(ctx)
    quick_add = _quick_add_block(connected_sites, existing_site_ids, site_problems, has_cache)

    new_brand_form = ui.Card(
        title="New brand",
        content=ui.Form(
            action="create_brand_profile",
            submit_label="Create brand",
            children=[
                ui.Input(param_name="brand_name", placeholder="Brand name"),
                ui.Input(param_name="industry", placeholder="Industry (optional)"),
                ui.Input(param_name="site_id", placeholder="Content Strategy Hub site_id (optional)"),
            ],
        ),
    )

    if not docs:
        empty_children = [
            ui.Empty(
                message="No brands yet — create one below to start a SWOT / gap analysis.",
                icon="🎯",
            ),
        ]
        empty_children.append(quick_add)
        empty_children.append(new_brand_form)
        return ui.Stack(direction="v", gap=3, children=empty_children)

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

    children = [ui.List(items=items, searchable=True), quick_add, new_brand_form]

    return ui.Stack(direction="v", gap=3, children=children)


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

    # P0 manual UI spike: this is intentionally a local projection only.
    # It must not call downstream apps while rendering because renderer-time
    # IPC may lose authenticated user context.
    vbs_workspace = await _workspace_for_brand(ctx, brand_id)
    actor_id, tenant_id = _actor(ctx)
    vbs_membership = await _membership_for_actor(ctx, vbs_workspace) if vbs_workspace else None
    vbs_workspace_owned = bool(vbs_membership)
    vbs_can_manage_access = bool(vbs_membership and vbs_membership.get("role") == "owner")
    vbs_legacy_owner_can_migrate = bool(
        vbs_workspace
        and not vbs_membership
        and vbs_workspace.data.get("access_model_version", 1) < 2
        and vbs_workspace.data.get("tenant_id") == tenant_id
        and vbs_workspace.data.get("owner_id") == actor_id
    )
    vbs_page = None
    vbs_audit_page = None
    vbs_evidence_page = None
    vbs_profile_page = None
    vbs_membership_page = None
    vbs_incident_page = None
    if vbs_workspace_owned:
        vbs_page = await ctx.store.query(VBS_SYSTEMS, where={"brand_id": brand_id}, order_by="-revision", limit=50)
        vbs_audit_page = await ctx.store.query(VBS_AUDIT_EVENTS, where={"brand_id": brand_id}, order_by="-occurred_at", limit=50)
        vbs_evidence_page = await ctx.store.query(VBS_EVIDENCE, where={"brand_id": brand_id}, order_by="-created_at", limit=50)
        vbs_profile_page = await ctx.store.query(VBS_PROFILES, where={"brand_id": brand_id}, order_by="-revision", limit=50)
        vbs_membership_page = await ctx.store.query(VBS_MEMBERSHIPS, where={"brand_id": brand_id}, order_by="-created_at", limit=100)
        vbs_incident_page = await ctx.store.query(VBS_AUDIT_INCIDENTS, where={"brand_id": brand_id}, order_by="-created_at", limit=50)

    comp_page = await ctx.store.query(
        "competitor_profiles", where={"brand_id": brand_id}, order_by="-created_at", limit=200
    )
    competitors = [{"id": d.id, **d.data} for d in comp_page.data]

    seg_page = await ctx.store.query(
        "target_segments", where={"brand_id": brand_id}, order_by="-created_at", limit=200
    )
    segments = list(seg_page.data)

    swot_page = await ctx.store.query("swot_results", where={"brand_id": brand_id}, order_by="-created_at", limit=500)
    current_swot_docs = [d for d in swot_page.data if d.data.get("is_current", True)]
    latest_swot = current_swot_docs[0].data if current_swot_docs else None
    latest_swot_id = current_swot_docs[0].id if current_swot_docs else ""

    gap_page = await ctx.store.query("gap_analysis_results", where={"brand_id": brand_id}, order_by="-created_at", limit=500)
    current_gap_docs = [d for d in gap_page.data if d.data.get("is_current", True)]
    latest_gap = current_gap_docs[0].data if current_gap_docs else None
    latest_gap_id = current_gap_docs[0].id if current_gap_docs else ""

    header = ui.Header(brand_name, level=2, subtitle=data.get("industry", "") or "Brand")

    # Every action lives inside the tab it affects, never in a bar that is
    # visible on every tab. A refresh_panels=["brand_detail"] re-fetch keeps
    # the currently-accumulated `tab` param unchanged -- so a button that
    # runs a write and is shown on, say, the Profile tab would refresh the
    # panel back onto Profile, and the user would never see the SWOT tab
    # actually update. Keeping "Run SWOT Analysis" inside the SWOT tab
    # itself (mirroring the Gap Analysis tab's own embedded form) guarantees
    # the user is already looking at the tab that will show the result.
    action_bar = None

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
            ui.Card(
                title="Edit profile",
                content=ui.Form(
                    action="update_brand_profile",
                    submit_label="Save changes",
                    defaults={"brand_id": brand_id},
                    children=[
                        ui.Input(param_name="brand_name", placeholder="Brand name",
                                 value=data.get("brand_name", "")),
                        ui.Input(param_name="industry", placeholder="Industry",
                                 value=data.get("industry", "")),
                        ui.TextArea(param_name="mission", placeholder="Mission",
                                    value=data.get("mission", ""), rows=2),
                        ui.TextArea(param_name="vision", placeholder="Vision",
                                    value=data.get("vision", ""), rows=2),
                        ui.TextArea(param_name="value_proposition", placeholder="Value proposition",
                                    value=data.get("value_proposition", ""), rows=2),
                        ui.Input(param_name="tone_of_voice", placeholder="Tone of voice",
                                 value=data.get("tone_of_voice", "")),
                        ui.TagInput(param_name="unique_selling_points",
                                    values=data.get("unique_selling_points", []),
                                    placeholder="Add a USP and press Enter"),
                    ],
                ),
            ),
            ui.Card(
                title="Send to Content Strategy Hub",
                subtitle="Reshapes this brand into create_site_profile's fields",
                content=ui.Form(
                    action="build_content_strategy_handoff",
                    submit_label="Build handoff",
                    defaults={"brand_id": brand_id},
                    children=[
                        ui.Input(param_name="site_id", placeholder="Site id, e.g. g4s.md",
                                 value=data.get("site_id", "")),
                        ui.Input(param_name="domain", placeholder="Domain (optional, defaults to site id)"),
                        ui.TagInput(param_name="target_languages",
                                    placeholder="Add a language code (e.g. ru) and press Enter"),
                    ],
                ),
            ),
        ],
    )

    # ── Visual System tab — P0 manual UI spike ──────────────────────
    # No people, consent, external evidence or media actions are exposed
    # here. This spike validates the safe manual control path for a brand-
    # scoped, versioned non-personal strategic record first.
    if not vbs_workspace:
        vbs_tab = ui.Stack(
            direction="v", gap=3,
            children=[
                ui.Alert(
                    title="VBS workspace not initialized",
                    message=(
                        "Visual Brand System data is private and remains unavailable until "
                        "the current owner explicitly claims this brand workspace."
                    ),
                    type="info",
                ),
                ui.Card(
                    title="Initialize private workspace",
                    content=ui.Stack(
                        direction="v", gap=2,
                        children=[
                            ui.Alert(
                                title="Explicit owner action",
                                message=(
                                    "Initializing binds this VBS workspace to your authenticated "
                                    "tenant and user. It cannot be silently claimed by a panel read."
                                ),
                                type="warning",
                            ),
                            ui.Button(
                                "I am the workspace owner — initialize",
                                variant="primary",
                                on_click=ui.Call(
                                    "initialize_visual_brand_workspace",
                                    brand_id=brand_id,
                                    confirm_owner_claim=True,
                                ),
                            ),
                        ],
                    ),
                ),
            ],
        )
    elif vbs_legacy_owner_can_migrate:
        vbs_tab = ui.Stack(
            direction="v", gap=3,
            children=[
                ui.Alert(
                    title="Access model migration required",
                    message="This legacy VBS workspace still uses its founding-owner record. Migrate it explicitly to enable the private membership model; no VBS, evidence or Profile content will change.",
                    type="info",
                ),
                ui.Form(
                    action="migrate_visual_brand_access",
                    submit_label="Migrate workspace access",
                    defaults={
                        "brand_id": brand_id,
                        "expected_workspace_version": vbs_workspace.data.get("version", 1),
                    },
                    children=[],
                ),
            ],
        )
    elif not vbs_workspace_owned:
        vbs_tab = ui.Alert(
            title="VBS workspace unavailable",
            message="This brand's VBS workspace belongs to another private tenant or user.",
            type="warning",
        )
    else:
        vbs_revisions = list(vbs_page.data) if vbs_page else []
        vbs_audit_events = list(vbs_audit_page.data) if vbs_audit_page else []
        vbs_evidence = list(vbs_evidence_page.data) if vbs_evidence_page else []
        vbs_profiles = list(vbs_profile_page.data) if vbs_profile_page else []
        vbs_memberships = list(vbs_membership_page.data) if vbs_membership_page else []
        vbs_incidents = [
            item for item in (vbs_incident_page.data if vbs_incident_page else [])
            if item.data.get("tenant_id") == vbs_workspace.data["tenant_id"]
        ]
        vbs_integrity = await _verify_vbs_audit_integrity(ctx, vbs_workspace)
        vbs_integrity_failed = not vbs_integrity.valid
        vbs_role = vbs_membership.get("role", "viewer")
        vbs_can_edit = not vbs_integrity_failed and "edit" in ROLE_PERMISSIONS.get(vbs_role, set())
        vbs_can_review = not vbs_integrity_failed and "review" in ROLE_PERMISSIONS.get(vbs_role, set())
        vbs_can_manage_access = not vbs_integrity_failed and vbs_can_manage_access
        current_vbs = next((d for d in vbs_revisions if d.data.get("status") == "approved_current"), None)
        current_profile = next((d for d in vbs_profiles if d.data.get("status") == "approved_current"), None)
        revision_rows = [
            ui.Card(
                title=f"Revision {d.data.get('revision', '?')} · {d.data.get('status', 'draft')}",
                subtitle=d.data.get("visual_intent", "No visual intent recorded"),
                content=ui.KeyValue(columns=1, items=[
                    {"key": "Realism", "value": d.data.get("realism_level") or "—"},
                    {"key": "Core rules", "value": "; ".join(d.data.get("core_rules", [])) or "—"},
                    {"key": "Avoid", "value": "; ".join(d.data.get("prohibited_patterns", [])) or "—"},
                    {"key": "Change note", "value": d.data.get("change_note") or "—"},
                ]),
                footer=(
                    ui.Form(
                        action="activate_visual_brand_system",
                        submit_label="Approve as current",
                        defaults={
                            "vbs_id": d.id,
                            "expected_revision": d.data.get("revision", 1),
                            "expected_workspace_version": vbs_workspace.data.get("version", 1),
                        },
                        children=[ui.TextArea(param_name="approval_note", placeholder="Approval note (optional)", rows=2)],
                    ) if vbs_can_review and d.data.get("status") in {"draft", "in_review"} else None
                ),
            ) for d in vbs_revisions
        ]
        vbs_tab = ui.Stack(
            direction="v", gap=3,
            children=[
                ui.Alert(
                    title="Critical changes paused — audit integrity check failed",
                    message="The VBS audit seal, ordered hash chain, or workspace anchor no longer matches. Draft approvals, evidence decisions and access changes are blocked until this is investigated. Use the read-only audit verification below; it does not alter records.",
                    type="error",
                ) if vbs_integrity_failed else ui.Alert(
                    title="Audit integrity status",
                    message=vbs_integrity.message,
                    type="success",
                ),
                ui.Card(
                    title="Acknowledge integrity incident",
                    subtitle="Records that an owner reviewed the mismatch. It never changes audit history or removes the critical-change block.",
                    content=ui.Form(
                        action="acknowledge_visual_brand_audit_incident",
                        submit_label="Record acknowledgement",
                        defaults={
                            "brand_id": brand_id,
                            "expected_workspace_version": vbs_workspace.data.get("version", 1),
                        },
                        children=[ui.TextArea(param_name="acknowledgement_note", placeholder="What was reviewed? This does not clear the block.", rows=2)],
                    ),
                ) if vbs_integrity_failed and vbs_membership.get("role") == "owner" else None,
                ui.Card(
                    title=f"Integrity incident history ({len(vbs_incidents)})",
                    subtitle="Owner acknowledgements are retained for review and never clear the safety block.",
                    content=ui.Stack(
                        direction="v", gap=1,
                        children=[
                            ui.KeyValue(columns=1, items=[
                                {"key": "Invalid audit event", "value": incident.data.get("invalid_event_id", "—")},
                                {"key": "Acknowledged by", "value": incident.data.get("acknowledged_by", "—")},
                                {"key": "Note", "value": incident.data.get("acknowledgement_note", "—")},
                            ]) for incident in vbs_incidents
                        ] or [ui.Text("No integrity incidents have been acknowledged.")],
                    ),
                ),
                ui.Card(
                    title="Workspace state",
                    content=ui.KeyValue(columns=2, items=[
                        {"key": "Workspace version", "value": str(vbs_workspace.data.get("version", 1))},
                        {"key": "Current revision", "value": str(current_vbs.data.get("revision")) if current_vbs else "Not approved"},
                        {"key": "Scope", "value": "P0: non-personal visual rules only"},
                        {"key": "People/media", "value": "Blocked pending privacy/storage spikes"},
                    ]),
                ),
                ui.Card(
                    title="Private workspace access",
                    subtitle="P0 uses known Imperal user IDs only. Roles are enforced server-side; no email lookup or cross-tenant invitations.",
                    content=ui.Form(
                        action="set_brand_membership",
                        submit_label="Save member role",
                        defaults={
                            "brand_id": brand_id,
                            "expected_workspace_version": vbs_workspace.data.get("version", 1),
                        },
                        children=[
                            ui.Input(param_name="user_id", placeholder="Known Imperal user ID"),
                            ui.Select(
                                param_name="role",
                                options=[
                                    {"value": "owner", "label": "Owner — manage access, edit, review"},
                                    {"value": "editor", "label": "Editor — create drafts and evidence"},
                                    {"value": "reviewer", "label": "Reviewer — approve and review evidence"},
                                    {"value": "viewer", "label": "Viewer — read-only"},
                                ],
                                placeholder="Choose role",
                            ),
                        ],
                    ) if vbs_can_manage_access else ui.Alert(
                        title="Read-only access",
                        message="Only a workspace owner can manage private brand memberships.",
                        type="info",
                    ),
                    footer=ui.Stack(
                        direction="v", gap=2,
                        children=[
                            ui.Card(
                                title=f"{item.data.get('user_id', 'Unknown member')} · {item.data.get('role', 'viewer')}",
                                subtitle="Active private workspace membership",
                                footer=ui.Form(
                                    action="revoke_brand_membership",
                                    submit_label="Revoke access",
                                    defaults={
                                        "brand_id": brand_id,
                                        "user_id": item.data.get("user_id", ""),
                                        "expected_workspace_version": vbs_workspace.data.get("version", 1),
                                    },
                                    children=[],
                                ) if vbs_can_manage_access and item.data.get("user_id") != vbs_workspace.data.get("owner_id") else None,
                            ) for item in vbs_memberships
                        ] or [ui.Text("No explicit member records yet; the founding owner retains access.")],
                    ),
                ),
                ui.Card(
                    title="Create next VBS draft",
                    subtitle="Saving creates a new revision; it does not overwrite history.",
                    content=ui.Form(
                        action="create_visual_brand_system",
                        submit_label="Save draft revision",
                        defaults={
                            "brand_id": brand_id,
                            "expected_workspace_version": vbs_workspace.data.get("version", 1),
                        },
                        children=[
                            ui.TextArea(param_name="visual_intent", placeholder="Visual intent: what should this brand's visuals make people feel or understand?", rows=3),
                            ui.Input(param_name="realism_level", placeholder="Realism level, e.g. grounded realism"),
                            ui.TagInput(param_name="core_rules", placeholder="Add a non-negotiable visual rule and press Enter"),
                            ui.TagInput(param_name="prohibited_patterns", placeholder="Add a prohibited pattern and press Enter"),
                            ui.TextArea(param_name="change_note", placeholder="Why this revision is needed (optional)", rows=2),
                        ],
                    ),
                ),
                ui.Card(
                    title="Register evidence reference",
                    subtitle="P0 stores a public HTTPS reference only. It never fetches, downloads or processes the source.",
                    content=ui.Form(
                        action="register_visual_evidence",
                        submit_label="Register unreviewed reference",
                        defaults={
                            "brand_id": brand_id,
                            "expected_workspace_version": vbs_workspace.data.get("version", 1),
                        },
                        children=[
                            ui.Input(param_name="source_url", placeholder="https://public-source.example/research"),
                            ui.Input(param_name="source_title", placeholder="Source title (optional)"),
                            ui.TextArea(param_name="observation", placeholder="What does this source appear to support? This remains unreviewed.", rows=3),
                        ],
                    ),
                ),
                ui.Card(
                    title=f"Evidence references ({len(vbs_evidence)})",
                    subtitle="All are private, unreviewed references — not verified claims or downloadable files.",
                    content=ui.Stack(
                        direction="v", gap=2,
                        children=[
                            ui.Card(
                                title=evidence.data.get("source_title") or evidence.data.get("source_url", "Reference"),
                                subtitle=evidence.data.get("source_url", ""),
                                content=ui.KeyValue(columns=1, items=[
                                    {"key": "Status", "value": evidence.data.get("status", "discovered")},
                                    {"key": "Observation", "value": evidence.data.get("observation", "—")},
                                    {"key": "Review note", "value": evidence.data.get("review_note", "—")},
                                ]),
                                footer=ui.Form(
                                    action="review_visual_evidence",
                                    submit_label="Save review decision",
                                    defaults={
                                        "evidence_id": evidence.id,
                                        "expected_status": evidence.data.get("status", "discovered"),
                                        "expected_workspace_version": vbs_workspace.data.get("version", 1),
                                    },
                                    children=[
                                        ui.Select(
                                            param_name="decision",
                                            options=[
                                                {"value": "reviewed_valid", "label": "Reviewed valid"},
                                                {"value": "hypothesis", "label": "Mark as hypothesis"},
                                                {"value": "rejected", "label": "Reject"},
                                                {"value": "archived", "label": "Archive"},
                                            ],
                                            placeholder="Choose review decision",
                                        ),
                                        ui.TextArea(param_name="review_note", placeholder="Required: explain the decision", rows=2),
                                    ],
                                ) if evidence.data.get("status", "discovered") != "archived" else None,
                            ) for evidence in vbs_evidence
                        ],
                    ) if vbs_evidence else ui.Empty(message="No evidence references yet. Add only public HTTPS sources you want to review later.", icon="Link"),
                ),
                ui.Card(
                    title="Create Visual Profile draft",
                    subtitle=(
                        "Binds a non-personal profile snapshot to the approved VBS and selected private evidence."
                        if current_vbs else "Approve a VBS revision first; profiles never guess a baseline."
                    ),
                    content=ui.Form(
                        action="create_visual_profile",
                        submit_label="Save profile draft",
                        defaults={
                            "brand_id": brand_id,
                            "expected_workspace_version": vbs_workspace.data.get("version", 1),
                        },
                        children=[
                            ui.TagInput(param_name="evidence_ids", placeholder="Optional evidence ID and Enter"),
                            ui.TextArea(param_name="profile_summary", placeholder="Non-personal visual profile summary", rows=3),
                            ui.TextArea(param_name="art_direction", placeholder="Non-personal art direction (optional)", rows=2),
                            ui.TextArea(param_name="change_note", placeholder="Why this profile revision is needed (optional)", rows=2),
                        ],
                    ) if current_vbs else ui.Alert(
                        title="Approved VBS required",
                        message="Visual Profiles can only be created from the current approved VBS baseline.",
                        type="info",
                    ),
                ),
                ui.Card(
                    title=f"Visual Profiles ({len(vbs_profiles)})",
                    subtitle=(
                        f"Current profile: revision {current_profile.data.get('revision')}" if current_profile
                        else "No approved current Visual Profile. Downstream resolution remains blocked."
                    ),
                    content=ui.Stack(
                        direction="v", gap=2,
                        children=[
                            ui.Card(
                                title=f"Profile revision {profile.data.get('revision', '?')} · {profile.data.get('status', 'draft')}",
                                subtitle=profile.data.get("profile_summary", ""),
                                content=ui.KeyValue(columns=1, items=[
                                    {"key": "VBS baseline", "value": f"Revision {profile.data.get('vbs_revision', '?')}"},
                                    {"key": "Evidence", "value": str(len(profile.data.get('evidence_ids', [])))},
                                    {"key": "Snapshot hash", "value": profile.data.get("snapshot_hash", "—")},
                                ]),
                                footer=ui.Form(
                                    action="activate_visual_profile",
                                    submit_label="Approve as current profile",
                                    defaults={
                                        "profile_id": profile.id,
                                        "expected_revision": profile.data.get("revision", 1),
                                        "expected_workspace_version": vbs_workspace.data.get("version", 1),
                                    },
                                    children=[ui.TextArea(param_name="approval_note", placeholder="Approval note (optional)", rows=2)],
                                ) if profile.data.get("status") in {"draft", "in_review"} else None,
                            ) for profile in vbs_profiles
                        ],
                    ) if vbs_profiles else ui.Empty(message="No Visual Profile drafts yet.", icon="Layers"),
                ),
                ui.Card(
                    title=f"Revision history ({len(vbs_revisions)})",
                    content=ui.Stack(direction="v", gap=2, children=revision_rows) if revision_rows else ui.Empty(message="No VBS revisions yet — create the first draft above.", icon="Palette"),
                ),
                ui.Card(
                    title="Audit-chain status",
                    subtitle="Read-only workspace anchor for chained audit events. A mismatch blocks critical changes.",
                    content=ui.KeyValue(columns=3, items=[
                        {"key": "Chain sequence", "value": str(vbs_integrity.chain_sequence)},
                        {"key": "Chained events", "value": str(vbs_integrity.chained_events)},
                        {"key": "Anchor fingerprint", "value": (vbs_integrity.chain_head[:12] + "…") if vbs_integrity.chain_head else "Not started"},
                    ]),
                ),
                ui.Card(
                    title=f"Audit trail ({len(vbs_audit_events)})",
                    subtitle="Append-only P0 record of workspace, draft and approval actions. Sealed entries can be verified without changing them.",
                    footer=ui.Form(
                        action="verify_visual_brand_audit_integrity",
                        submit_label="Verify sealed audit integrity",
                        defaults={"brand_id": brand_id},
                        children=[],
                    ),
                    content=ui.Stack(
                        direction="v", gap=1,
                        children=[
                            ui.Text(
                                f"{event.data.get('occurred_at', '')} · {event.data.get('event_type', 'event')} · {event.data.get('details', '')}",
                                variant="caption",
                            ) for event in vbs_audit_events
                        ],
                    ) if vbs_audit_events else ui.Empty(message="No VBS audit events yet.", icon="History"),
                ),
            ],
        )

    # ── SWOT tab ─────────────────────────────────────────────────────
    run_swot_button = ui.Button(
        "Run SWOT Analysis", variant="primary", icon="Sparkles",
        on_click=ui.Call("run_swot_analysis", brand_id=brand_id),
    )
    if latest_swot:
        archive_swot_button = ui.Button(
            "Mark as outdated", variant="secondary", icon="Archive",
            on_click=ui.Call("archive_swot_result", swot_id=latest_swot_id),
        )
        swot_tab = ui.Stack(
            direction="v", gap=3,
            children=[
                ui.Badge(label="Current", color="green"),
                ui.Grid(
                    columns=2, gap=3,
                    children=[
                        ui.Card(title="Strengths", content=_swot_list(latest_swot.get("strengths", []))),
                        ui.Card(title="Weaknesses", content=_swot_list(latest_swot.get("weaknesses", []))),
                        ui.Card(title="Opportunities", content=_swot_list(latest_swot.get("opportunities", []))),
                        ui.Card(title="Threats", content=_swot_list(latest_swot.get("threats", []))),
                    ],
                ),
                ui.Card(title="Run again (auto-supersedes this one)", content=run_swot_button),
                ui.Card(title="Or mark this one outdated by hand", content=archive_swot_button),
            ],
        )
    else:
        swot_tab = ui.Stack(
            direction="v", gap=3,
            children=[
                ui.Empty(message="No SWOT analysis yet -- run one below.", icon="Sparkles"),
                ui.Card(title="Run SWOT analysis", content=run_swot_button),
            ],
        )

    # ── Gap analysis tab ─────────────────────────────────────────────
    segment_options = [
        {"value": d.id, "label": d.data.get("segment_name", "") or d.id} for d in segments
    ]
    gap_form = (
        ui.Form(
            action="run_gap_analysis",
            submit_label="Run gap analysis",
            defaults={"brand_id": brand_id},
            children=[
                ui.Select(param_name="segment_id", options=segment_options,
                          placeholder="Choose a target segment"),
            ],
        )
        if segment_options else
        ui.Alert(
            title="No target segments yet",
            message="Add a target segment in the Segments tab first, then come back here to run the gap analysis.",
            type="info",
        )
    )
    if latest_gap:
        archive_gap_button = ui.Button(
            "Mark as outdated", variant="secondary", icon="Archive",
            on_click=ui.Call("archive_gap_analysis", gap_analysis_id=latest_gap_id),
        )
        gap_tab = ui.Stack(
            direction="v", gap=3,
            children=[
                ui.Badge(label="Current", color="green"),
                ui.Card(title="Gaps between brand and audience", content=_swot_list(latest_gap.get("gaps", []))),
                ui.Card(title="Recommendations to fill the gap", content=_swot_list(latest_gap.get("recommendations", []))),
                ui.Card(title="Run again for another segment", content=gap_form),
                ui.Card(title="Or mark this one outdated by hand", content=archive_gap_button),
            ],
        )
    else:
        gap_tab = ui.Stack(
            direction="v", gap=3,
            children=[
                ui.Empty(message="No gap analysis yet -- pick a segment below and run one.", icon="Target"),
                ui.Card(title="Run gap analysis", content=gap_form),
            ],
        )

    # ── Competitors tab ──────────────────────────────────────────────
    if competitors:
        comp_items = [
            ui.ListItem(
                id=c.get("id", ""),
                title=c.get("name", ""),
                subtitle=c.get("url", ""),
                meta=f"{len(c.get('strengths', []))} strengths · {len(c.get('weaknesses', []))} weaknesses",
                actions=[{
                    "icon": "Trash2",
                    "on_click": ui.Call("delete_brand_competitor", competitor_id=c.get("id", "")),
                    "confirm": f"Delete competitor '{c.get('name', '')}'? This cannot be undone.",
                }],
            )
            for c in competitors
        ]
        competitors_list = ui.List(items=comp_items, searchable=True)
    else:
        competitors_list = ui.Empty(message="No competitors tracked yet.", icon="Users")

    add_competitor_form = ui.Card(
        title="Add competitor",
        content=ui.Form(
            action="add_brand_competitor",
            submit_label="Add competitor",
            defaults={"brand_id": brand_id},
            children=[
                ui.Input(param_name="name", placeholder="Competitor name"),
                ui.Input(param_name="url", placeholder="Website (optional)"),
                ui.TagInput(param_name="strengths", placeholder="Add a strength and press Enter"),
                ui.TagInput(param_name="weaknesses", placeholder="Add a weakness and press Enter"),
                ui.TextArea(param_name="notes", placeholder="Notes (optional)", rows=2),
            ],
        ),
    )
    competitors_tab = ui.Stack(direction="v", gap=3, children=[competitors_list, add_competitor_form])

    # ── Segments tab ─────────────────────────────────────────────────
    if segments:
        seg_items = [
            ui.ListItem(
                id=d.id,
                title=d.data.get("segment_name", "") or d.id,
                subtitle=d.data.get("demographics", ""),
                meta=f"{len(d.data.get('pain_points', []))} pain points · {len(d.data.get('needs', []))} needs",
                actions=[{
                    "icon": "Trash2",
                    "on_click": ui.Call("delete_target_segment", segment_id=d.id),
                    "confirm": f"Delete segment '{d.data.get('segment_name', d.id)}'? This cannot be undone.",
                }],
            )
            for d in segments
        ]
        segments_list = ui.List(items=seg_items, searchable=True)
    else:
        segments_list = ui.Empty(message="No target segments defined yet.", icon="Users")

    add_segment_form = ui.Card(
        title="Add target segment",
        content=ui.Form(
            action="create_target_segment",
            submit_label="Add segment",
            defaults={"brand_id": brand_id},
            children=[
                ui.Input(param_name="segment_name", placeholder="Segment name, e.g. 'SMB office managers'"),
                ui.Input(param_name="demographics", placeholder="Demographics (optional)"),
                ui.Input(param_name="psychographics", placeholder="Psychographics (optional)"),
                ui.TagInput(param_name="pain_points", placeholder="Add a pain point and press Enter"),
                ui.TagInput(param_name="needs", placeholder="Add a need and press Enter"),
                ui.TagInput(param_name="preferred_channels", placeholder="Add a channel and press Enter"),
            ],
        ),
    )
    segments_tab = ui.Stack(direction="v", gap=3, children=[segments_list, add_segment_form])

    tab_defs = [
        ("profile", "Profile", profile_tab),
        ("visual_system", "Visual System", vbs_tab),
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
        children=[header, ui.Divider(), tab_switcher, active_content],
    )


def _swot_list(items: list) -> object:
    if not items:
        return ui.Empty(message="(none identified)", icon="—")
    return ui.Markdown("\n".join(f"- {i}" for i in items))
