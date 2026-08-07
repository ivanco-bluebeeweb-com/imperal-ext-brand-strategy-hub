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

**Status:** `DEPLOYED — manual live proof required`.

---

## Follow-on slices — only after VBS-0 is proven

### P1-B — visible VBS → Content Strategy receipt

**User-visible result:** a user can see in Content Strategy exactly which approved Visual Profile was received, its VBS/profile revisions, snapshot fingerprint and `current` / `stale` state.

**Existing partial implementation:** provenance and baseline checks exist in code. This slice is considered complete only when VBS-0 and the Content Strategy receipt are demonstrated in the panel together.

### P1-C — read-only downstream handoff review

**User-visible result:** before leaving Content Strategy, the user sees the compact payload that Writer or Media Studio would receive: guidance, provenance, baseline state and the no-generation/provider-policy boundary.

**Not in scope:** creating Media Studio packages, images, uploads or publishing.

### P2 — asset and generation decision (not planned for implementation)

This requires a separate approved product decision and a new design for storage, permissions, retention, provenance, consent/licensing, provider failure policy and human approval. No implementation is authorised by this plan.

---

## Explicit non-goals until a separate decision

- Image generation, image editing, asset upload or WordPress media upload.
- Personal imagery, face recognition, face swap, synthetic likeness or consent collection.
- Automatic VBS or tax/legal/creative approval.
- Reopening audit-chain hardening without a newly observed defect.

---

## Reporting standard for each slice

Every report must say only:

1. What became visible in the Imperal panel;
2. where to see it;
3. the commit pushed;
4. tests/build/validation result;
5. the next single visible slice.

A passing test suite or commit alone is maintenance evidence, not completed user-facing delivery.
