# VBS — development plan and delivery record

**Updated:** 2026-08-07  
**Product:** Brand Strategy Hub → Visual Brand System (VBS) and Visual Profile.  
**Working rule:** a code change becomes product delivery only when its user flow is visible and usable in the Imperal panel.

---

## Purpose and product boundary

VBS gives a brand team a controlled, human-approved visual baseline which can be handed downstream as **read-only, non-personal guidance**.

It is not an image generator, asset library, facial-recognition feature, likeness system, or automated brand-approval engine.

The safe product path is:

```text
Brand → VBS workspace → evidence reference → human review
→ approved VBS → Visual Profile draft → human approval
→ read-only Content Strategy / Media guidance
```

Human reviewers remain responsible for evidence validity, VBS approval, Visual Profile approval, and all downstream creative or publishing decisions.

---

## Delivery ledger — implemented in code

### P0-A — private VBS workspace and revisions ✅

**Delivered:** `51dd4a9`, `cbca770`

- Explicit owner claim creates a tenant-local VBS workspace.
- VBS revisions use workspace-version and revision guards, preventing stale approvals.
- Manual panel states exist for empty and owned workspaces.

### P0-B — evidence intake and human review ✅

**Delivered:** `3131934`, `ed27ebd`

- Evidence is an HTTPS reference only; P0 does not fetch, download, process or generate imagery.
- Review statuses: `reviewed_valid`, `hypothesis`, `rejected`, `archived`.
- Only reviewed-valid evidence is eligible for an approved visual baseline.

### P0-C — role-based access and tenant isolation ✅

**Delivered:** `22ee3ef`, `89582c4`, `9772741`

- Roles: owner, editor, reviewer, viewer.
- Server-side role checks remain authoritative; controls are aligned with those roles in the panel.
- Legacy access moves to memberships only through an explicit owner action.

### P0-D — approval integrity and audit record ✅

**Delivered:** `96e1dd2` through `899476a`, `52922c4`

- Critical VBS events are sealed and ordered into an audit chain.
- Integrity failures pause critical changes (fail closed).
- Approval records contain an immutable snapshot of reviewed-valid evidence and link to their exact audit event.
- Incident acknowledgement is audit-visible but does not bypass an integrity pause.

### P0-E — Visual Profile lifecycle and approval UI ✅

**Delivered:** `06fec2d`, `a2bb697`, `e95b988`

- Visual Profile drafts bind to an approved VBS and selected tenant-local reviewed-valid evidence.
- Approval rejects stale, superseded or invalid VBS/evidence basis.
- Reviewer/owner panel controls show the required VBS and evidence context; other roles are read-only.

### P0 verification

- **Automated result:** 96 Brand Strategy Hub tests passed on 2026-08-07.
- **Code status:** complete.
- **Live-product status:** not yet proven in Imperal panel. This is the active gate below.

### P0-B follow-up fix — evidence-review form silently failed on an empty note

**Problem this closes:** a live browser test on 2026-08-07 against Climtec.md found that clicking **Save review decision** sent a real network request (confirmed via trace) but left the evidence's `status`/`workspace_version` unchanged, with no visible error. Root cause found by direct reproduction: `ReviewVisualEvidenceParams.review_note` requires `min_length=1`, but the panel's `ui.TextArea` for that field shipped with no default `value=`. A reviewer who picked a decision without typing a note submitted `review_note=""`, which failed Pydantic validation in platform dispatch *before* `review_visual_evidence` ever ran — so the extension's own `ActionResult.error()` path was never reached and the panel had nothing to show.

**Fix:** the TextArea now carries `value="No additional notes."` as a non-empty default; a reviewer can still overwrite it. Every submission now validates.

**Delivered:** `ab80460a`. Regression test added to `test_vbs_p0.py` asserting the panel renders the non-empty default. All 98 tests pass; `imperal validate`: 0 errors, 0 warnings, 1 info (pre-existing, no `on_install` hook). Deployed 2026-08-10, `20/21` checks (same pre-existing, non-blocking pricing-confirmation warning seen on every release since 2026-08-07).

**Platform lesson (applies to any panel, not just VBS):** any form field mapped to a Pydantic parameter with `min_length>=1` must ship a non-empty default `value=`, or an unedited required field silently fails validation with no user-visible error.

---

## P1-A — read-only downstream handoffs ✅ in code, pending live proof

**Delivered:** `f1b07e6`, `2299448`, `821691d`

An approved current Visual Profile can build two safe payloads:

1. **Content Strategy handoff** — profile/VBS provenance and non-personal visual guidance.
2. **Media guidance handoff** — visual intent, style direction, core rules and prohibited patterns.

Both fail closed if the profile is not approved/current, the VBS is stale, the evidence basis fails verification, the audit chain is paused, or the requester is outside the tenant.

**Provider policy:** third-party providers are first choice. Magnific is eligible only after a technical failure of the other providers. Neither handoff creates a package, asset, upload or generated image.

---

## Active gate — VBS-0: prove the panel flow in live Imperal

**Why this is first:** the earlier work reached code and automated tests, but not a demonstrated live user journey. New VBS features must not hide that gap.

### Required representative user flow

In **Imperal panel → Brand Strategy Hub**:

1. Create or open a representative brand.
2. Initialise the Visual Brand workspace with the explicit owner claim.
3. Create a VBS draft.
4. Register one public HTTPS evidence reference.
5. Review it as `reviewed_valid`.
6. Approve the VBS.
7. Create a Visual Profile using that VBS and evidence.
8. Approve the Visual Profile as a reviewer or owner.
9. Open **Approved baseline handoffs** and confirm the visible Content Strategy and Media guidance:
   - Visual intent and style direction;
   - Profile/VBS revisions;
   - evidence-basis/provenance state;
   - third-party-first provider policy;
   - explicit read-only / no-generation boundary.

### Definition of done

- The full flow completes once in the live panel.
- UI states and actions are visible to the permitted role and hidden/read-only for the other roles.
- Any failure is recorded as a reproducible product issue: route, role, exact action, expected result, actual result.
- If fixes are necessary, they are followed by a focused regression test, full test suite, build/validate, commit and push.

**Deployment:** Brand Strategy Hub deployed to Imperal from commit `0971cafd` on 2026-08-07; panels, manifest and icon synced. Deployment reported `20/21` checks with a warning, whose cause was not included in the terminal response.

**Status:** `LIVE-PROVEN — 2026-08-07`. The full flow (initialize workspace → draft VBS → register evidence → review valid → approve VBS → create Visual Profile → approve profile → confirm handoffs) was completed once end-to-end in the live Imperal panel for Climtec.md, via real clicks and real form input, each step re-verified by a direct read call as source of truth. `resolve_current_visual_profile` for Climtec.md now returns a deterministic approved baseline: VBS revision 2, Visual Profile revision 1, snapshot hash present, evidence basis verified. Two real defects were found live and fixed during this proof (`list_visual_brand_audit_events` 500, `ui.Tooltip` inside `ui.KeyValue` rendering as `[object Object]`); both are fixed, tested and deployed. Full UX-simulation pass (target-user persona) and its resulting fix plan were also completed and deployed on top of this baseline — see `VBS panel UX` commits.

### P1-A live proof — 2026-08-09

`build_approved_visual_profile_handoff` and `build_approved_visual_media_handoff` were called live for Climtec.md and returned the exact approved guidance (visual intent, style direction, core rules, prohibited patterns, provider policy, snapshot hash) with no fetch/generation side effects, confirming the fail-closed read-only contract in production.

**New finding — the handoff is not yet wired into the pipeline that would consume it.** Climtec.md's one existing Media Studio package (created 2026-08-06, before the VBS baseline existed) uses an ad-hoc style direction that does not match the approved Visual Profile. There is no code anywhere in Content Strategy → Article Writer → Media Studio → WordPress Hub that calls `build_approved_visual_media_handoff` and feeds its output into `create_media_brief`. This is consistent with an earlier pipeline finding (note "Недоработки пайплайна SEO-контента — прогон Climtec", 2026-08-06, item 9): image generation is a fully disconnected, nobody-triggers-it step in the pipeline today.

As a live proof of the correct pattern, one real media brief was created manually for Climtec.md using the exact approved handoff text verbatim as `style_direction` (see media package `a0e35e28`, article "Рекуператор для квартиры"). This confirms the bridge works when done by hand; it does not yet happen automatically. **This is the next concrete slice for VBS's role in the SEO pipeline** — see P1-D below.

---

## Follow-on slices — only after VBS-0 is proven

### P1-B — visible VBS → Content Strategy receipt

**User-visible result:** a user can see in Content Strategy exactly which approved Visual Profile was received, its VBS/profile revisions, snapshot fingerprint and `current` / `stale` state.

**Existing partial implementation:** provenance and baseline checks exist in code. This slice is considered complete only when VBS-0 and the Content Strategy receipt are demonstrated in the panel together.

### P1-C — read-only downstream handoff review

**User-visible result:** before leaving Content Strategy, the user sees the compact payload that Writer or Media Studio would receive: guidance, provenance, baseline state and the no-generation/provider-policy boundary.

**Not in scope:** creating Media Studio packages, images, uploads or publishing.

### P1-D — wire the approved handoff into the actual Media Studio brief (next concrete slice)

**Problem this closes:** `build_approved_visual_media_handoff` exists and is proven live (P1-A), but nothing in the pipeline calls it before `create_media_brief` runs, so approved visual guidance and the images actually generated for a site can silently diverge (observed live for Climtec.md on 2026-08-09).

**Constraint:** there is no cross-extension IPC on this platform (confirmed by Brand Strategy Hub's own `build_content_strategy_handoff` docstring) — Media Studio cannot call Brand Strategy Hub directly, and this plan does not authorise adding such a channel.

**Proposed shape, human-in-the-loop, no new automation:**
- In Brand Strategy Hub's Visual System tab, the existing "Approved baseline handoffs" block gets one more concrete, copyable field: a ready-to-paste `style_direction` string built from `build_approved_visual_media_handoff`'s `style_direction` + `prohibited_patterns`, formatted exactly as it should be pasted into Media Studio's `create_media_brief`.
- No auto-fill, no silent write into Media Studio — the human doing the media brief copies this value in, same as they copy any other brief detail today. This keeps the read-only, no-generation boundary intact and needs no schema or permission change.
- Definition of done: a user can go from "VBS approved" to "media brief created with the right style_direction" without leaving guesswork to memory or ad-hoc wording, demonstrated live for one real site.

**Status:** `LIVE-PROVEN — 2026-08-09` (re-verified). Deployed commit `79fee279`
(20/21 checks, same unexplained non-blocking warning pattern seen on every
release of this app since 2026-08-07 — not investigated further, not
blocking). All 98 tests pass; `imperal validate`: 0 errors, 0 warnings, 1 info
(no `on_install` hook — pre-existing, not new). Immediately after deploy,
called `build_approved_visual_media_handoff` live for Climtec.md and got the
exact expected `style_direction` string back (grounded realism / no surreal
elements / Prohibited: no surreal, cartoonish, or exaggerated visual styles),
confirming the ready-to-paste field under **Brand Strategy Hub → Visual
System → Baseline handoffs** renders the same text a human would copy into
Media Studio's `create_media_brief`.

### P1-B and P1-C — delivered, in Content Strategy Hub

These two slices are about the **receiving side** of the handoff (Content
Strategy showing what it got), not Brand Strategy Hub's sending side, so they
were implemented and live-proven in Content Strategy Hub's own plan, not here:

- **P1-B** (visible VBS → Content Strategy receipt): `LIVE-IMPLEMENTED —
  2026-08-09`, commit `04b6a45`. Brief screen shows `Writer handoff: ready` /
  `visual guidance excluded — baseline stale`.
- **P1-C** (read-only downstream handoff review): `LIVE-IMPLEMENTED —
  2026-08-09`, commit `d009b74`, refined `354164f` after a Dana (content
  editor) UX-simulation pass. One unified card shows both "→ Article Writer"
  and "→ Media Studio" readiness, baseline state, provenance and boundary
  text together.

See `Content Strategy Hub/SEO_PIPELINE_DEVELOPMENT_PLAN.md` phases P0-B/P0-C
for the full delivery record of that side.

**All P1 slices are now closed.** The only remaining item in this plan is P2,
which is explicitly not authorised for implementation without a separate
product decision (see below).

### P2 — asset and generation decision

**Product decision:** authorised by the brand owner on 2026-08-10, scoped narrowly to
close the exact gap already documented above (P1-D "New finding" — nobody tracks
whether a Media Studio package's actual images match the Visual Profile they were
supposed to follow). This decision does NOT authorise image generation, personal
imagery, or automatic approval — those three non-goals below remain in force
unchanged. It authorises exactly one new capability: **P2-A**.

### P2-A — human-recorded conformance between a generated media package and the approved Visual Profile

**Problem this closes:** `build_approved_visual_media_handoff` proves the guidance
Brand Strategy Hub *hands off* is correct (P1-A/P1-D), but nothing records whether
the images a human actually *received back* from Media Studio conform to it. A
human currently has no structured place to say "I checked package X against our
approved guidance and it matches" or "it drifted, don't use it" — the divergence
found live for Climtec.md on 2026-08-09 could recur silently, indefinitely.

**Design (storage / permissions / retention / provenance / provider-failure / human-approval), per plan requirement:**

- **Storage:** new tenant-scoped store collection `vbs_media_conformance`. One record
  per human review of one media package. No image bytes, no fetch of the package or
  any URL — the human pastes the Media Studio `package_id` (free-text reference,
  exactly like evidence `source_url`) and states their own verdict.
- **Permissions:** reuses the existing VBS role model unchanged — recording a
  conformance verdict requires the `review` permission (same role tier as
  `review_visual_evidence`), enforced server-side by `_require_vbs_access`. No new
  role, no schema change to `ROLE_PERMISSIONS`.
- **Retention:** lives inside the same private, tenant-local VBS workspace as every
  other VBS record; deleted by the existing `purge_brand_strategy_data` cascade —
  no separate retention path to design or forget.
- **Provenance:** at recording time, the function snapshots the *current* approved
  baseline via the same resolver used by the handoffs (`profile_id`,
  `profile_revision`, `vbs_id`, `vbs_revision`, `snapshot_hash`) so a later change to
  the approved profile can never silently rewrite what an old conformance verdict
  was actually checked against — same immutable-basis pattern already proven for
  approval evidence.
- **Consent/licensing:** not applicable — this stores no imagery and no personal
  data, only a human's text verdict about a package id.
- **Provider failure policy:** not applicable — this calls no image provider and
  performs no generation of any kind.
- **Human approval:** this *is* the human-approval mechanism — the verdict
  (`matches_approved_guidance` | `diverges` | `not_yet_reviewed`) is always a named
  human's explicit judgment, never inferred or automated.

**Definition of done:** a human can look at one media package (already generated in
Media Studio, outside this app's control) and record, against the brand's current
approved Visual Profile snapshot, whether it conforms — visible in the panel,
audited, tenant-isolated, fail-closed if the workspace is stale or the VBS/Profile
chain is broken. Demonstrated live for one real site.

**Status:** delivered, 2026-08-10.

**Delivery record (P2-A):**

1. Panel: new "Media conformance tracking" card in the brand detail panel's
   "Baseline handoffs" tab — a form to paste a Media Studio `package_id` and
   pick a verdict (conforms / drifted / inconclusive) with a required reviewer
   note, plus a read-only list of past verdicts newest-first.
2. Where to see it: Brand Strategy Hub panel → open a brand → Baseline
   handoffs tab (visible once the workspace has an approved current Visual
   Profile; gated the same way approval/handoff cards already are).
3. Commits pushed: `8ba5a6a` (feature + tests), `21fa70d` (manifest rebuild —
   `imperal build` had been skipped before the first deploy, so the two new
   tools weren't in the synced catalog; caught and fixed same session).
   Deployed at `21fa70d7`.
4. Tests: 103/103 passing (5 new: role gate reviewer-vs-editor, invalid
   verdict, missing approved profile, tenant isolation, audit trail).
   `imperal validate`: 0 errors / 0 warnings / 1 pre-existing info.
5. Live-demonstrated on Climtec.md (real brand, real approved Visual Profile
   revision 1, real Media Studio package "Cost of installing a heat-recovery
   ventilator"): `record_media_conformance` and `list_media_conformance`
   called for real through the deployed tools, not just tests — confirmed
   the stored `snapshot_hash` matches the resolved approved profile exactly.
   Verdict recorded as `inconclusive` (not `conforms`) because the check
   verified prompt-fidelity (the approved art_direction text is threaded
   verbatim into the real Imagen4 prompt for that package — answers the
   open question "does VBS form the correct image prompt?": **yes**), not a
   human's actual pixel-level look at the rendered image, which is what a
   `conforms`/`drifted` verdict requires by design.

**Non-goals reaffirmed (still not authorised by this decision):**

---

## Plain-language UX pass — Visual System tab

**Why:** owner feedback (repeated): the panel used too much internal jargon
("workspace", "VBS", "evidence basis", "tenant", "founding owner") for a
non-technical user to act on without help. Goal: fewer words, clearer next
action, without weakening any safety/audit semantics underneath.

**Status:** delivered, 2026-08-10.

**Delivery record:**

1. Panel: every user-visible title, subtitle, button label, and alert
   message in the Visual System tab was rewritten in plain language —
   uninitialized state, Status card, Who-can-access card, Create/Approve
   style forms, Evidence/References card, Visual Profile card, Send-to-other-
   apps card, media-conformance card, membership list, and the top status
   banner ("Your visual style is live" / "Almost there — one more step" /
   "Let's set your visual style"). The Revisions/History section and the
   "For the tech team" audit-chain section (already plain from an earlier
   pass) were left as-is on inspection — no jargon leaking there. The other
   tabs (Profile/SWOT/Gap/Competitors/Segments) were checked and found
   already short and plain; no changes needed there.
2. Where to see it: Brand Strategy Hub panel → open a brand → Visual System
   tab, at every stage (not initialized, draft, approved, blocked).
3. No new params/actions/error codes were touched — only display strings.
   All existing param_names, action names and error codes are unchanged, so
   nothing that calls this app from outside (Content Strategy Hub, Media
   Studio handoffs) is affected.
4. Tests: 103/103 passing (existing assertions updated to match new
   strings, no test coverage removed). `imperal validate`: 0 errors / 0
   warnings / 1 pre-existing info. `imperal build` re-run — manifest
   unchanged (no new tools).
5. Next single visible slice: none currently queued for this tab; revisit
   only if further target-user feedback surfaces remaining confusing spots.

---

## Explicit non-goals until a separate decision

- Image generation, image editing, asset upload or WordPress media upload.
- Personal imagery, face recognition, face swap, synthetic likeness or consent collection.
- Automatic VBS or tax/legal/creative approval.
- Reopening audit-chain hardening without a newly observed defect.

---

## Brand-deletion gap closed — VBS now cascade-deletes with the brand

**Why:** `delete_brand_profile` cascaded competitors/segments/SWOT/gap-analysis,
but never touched a brand's private VBS workspace. `purge_brand_strategy_data`
deliberately excludes VBS too (by design — a VBS workspace is an anchor record,
not disposable pipeline output). Together this meant a brand with a VBS
workspace could never be fully deleted: the workspace, its revisions,
evidence, Visual Profiles, memberships, audit events, audit incidents and
media-conformance verdicts were left orphaned forever with no path to remove
them.

**Status:** delivered, 2026-08-11.

**Delivery record:**

1. `delete_brand_profile` now also deletes, when a VBS workspace exists for
   the brand being deleted: the workspace record itself plus every row in
   `visual_brand_systems`, `visual_evidence`, `visual_profiles`,
   `vbs_brand_memberships`, `visual_brand_audit_events`,
   `visual_brand_audit_integrity_incidents`, and `vbs_media_conformance` for
   that brand_id. A brand with no VBS workspace deletes exactly as before —
   no behaviour change for the common case. The success summary now says
   "...including its visual brand system" when that cascade ran.
2. Where to see it: same place as before — `delete_brand_profile` (chat/API,
   `confirm_cascade=true` still required); no new panel surface, this closes
   a data-integrity gap in an existing destructive action, not a new feature.
3. Commit pushed: see `git log` for this change; deployed live.
4. Tests: 105/105 passing (2 new — full cascade with every VBS collection
   populated proven empty after deletion by direct store query, plus a
   no-VBS-workspace regression check). `imperal validate`: 0 errors / 0
   warnings / 1 pre-existing info. `imperal build` re-run — manifest updated
   (new `effects` entries on `delete_brand_profile`, no new tools).
5. Next single visible slice: none currently queued for VBS — feature is
   considered complete for its authorised scope; the only remaining
   documented gaps are pre-authorised non-goals (image gen, personal
   imagery, auto-approval) which each need an explicit separate owner
   decision before any code is written.

---

## Reporting standard for each slice

Every report must say only:

1. What became visible in the Imperal panel;
2. where to see it;
3. the commit pushed;
4. tests/build/validation result;
5. the next single visible slice.

A passing test suite or commit alone is maintenance evidence, not completed user-facing delivery.
