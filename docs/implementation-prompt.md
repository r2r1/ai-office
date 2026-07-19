# Implementation prompt — AI Office product redesign

**Audience:** a Claude Code agent session (possibly you, later, with no memory
of writing this). **Purpose:** turn the product decisions already made in
`docs/ai-office-canonical-spec.md` and `docs/product-portrait-2026-07-19.md`
into real, shipped code — one small verified iteration at a time.

Read this whole file before touching code. It exists so the next session
doesn't re-derive decisions that are already made, and doesn't attempt
everything at once.

---

## 0. Ground truth — read these, don't re-ask

- `docs/ai-office-canonical-spec.md` — 17-part RFC/architecture handbook.
  Part 1.2a is the ERP comparison (why this isn't just agentic ERP). Part 17
  is a self-audit (✅/🟡/❌/🔧/🗑 per subsystem) — check it before assuming a
  piece doesn't exist yet.
- `docs/product-portrait-2026-07-19.md` — 24 sections from a live interview
  with the founder, resolving dozens of concrete product questions (risk
  model, multi-user access, marketplace mechanics, onboarding sequence,
  threat model, ERP-differentiation follow-ups). Each section states a
  DECISION, not a proposal. Sections with ⚠️ flag places where a naive
  reading would get the decision wrong — read those markers, they exist
  because a first draft of that section was already corrected once.
- `CLAUDE.md` — operating invariants (Section 4) and module map (Section 3.7).
  These are load-bearing; nothing in this prompt overrides them.

**Do not re-interview the founder.** If you hit a question the portrait
already answers, use that answer. If you hit something genuinely new, make
the smallest reasonable call, document the assumption in the commit/handoff
entry, and move on — don't block a coding session on a product question that
can be revisited later. The portrait's own "Открытые вопросы" sections list
what's honestly still open; anything else is decided.

### 0.5 Frontend map — grounded, don't re-explore before reading this

`webapp/src/` is ~11k lines across 34 files. Before proposing a new screen
or component, check whether one of these already does 80% of the job —
extending beats inventing everywhere below.

- **State**: `data/OfficeProvider.tsx` — a module-level store (not plain
  Context) exposed via `useSyncExternalStore`, single `reducer(state,
  action)`, components read through `useOfficeSelector(selector)` to avoid
  whole-tree re-renders (this was a deliberate perf fix, keep using
  selectors for anything new). SSE via `EventSource("/events")`; `onopen`
  triggers a full resync, not just first connect. `data/api.ts` — thin
  fetch wrapper, ~70 named endpoint functions; add new backend reads here,
  don't hand-roll fetch calls in components.
- **Nav**: `app/components/NavRail.tsx` — 7 tabs (office/dashboard/project/
  team/results/resources/settings), defined in one `NAV` array. A new
  top-level tab is a big claim on IA — prefer a sub-tab inside an existing
  view (`SubTabs`/`useSubTab` from `ui.tsx`, already used by ResultsView
  and ResourcesView for exactly this).
- **Design primitives**: `app/views/ui.tsx` — `Card`, `Pill`, `Button`
  (primary/secondary/ghost/danger/toggle), `TextInput`/`TextArea`,
  `Disclosure`, `ShowMore`, `MercuryBar`, `STATUS_COLOR`, `Empty`,
  `ViewShell`/`ViewHead`/`ViewBody`. `styles/design.css` has the full
  token set (spacing, radii, semantic colors, dark/light). Use these, never
  a fresh inline `style={{border, radius, background}}` for a button/input
  (CLAUDE.md §5 names this exact anti-pattern from a past audit).
- **"Office voice" primitive already exists**: `app/components/
  RightPanel.tsx` → `FeedTab` renders the event log with `KIND_COLOR`
  (error/done/thinking/hired/speech/system → color) and a working
  **"🔍 Почему?" expandable block** (`decisionForFeed`) that already reads
  `/api/decisions` and renders confidence/alternatives/risks. This is the
  concrete UI seed for portrait §5b/§13 (office states its case with
  reasoning) — extend `KIND_COLOR` and the decision-matching logic for new
  event kinds (mistake acknowledgment, risk notice, capability unlock)
  rather than building a new panel. `ChatTab` in the same file is the real-
  time dialogue surface — this is where §3's "office argues, owner can push
  back, office revises" conversation actually happens today.
- **Marketplace catalog already exists, mostly**: `app/views/
  ConnectionsView.tsx` renders a "Каталог интеграций" grid grouped by
  category, `IntegCard` per provider (OAuth popup / Telegram MTProto modal
  / Bitrix24 portal-domain modal / API-key how-to), plus a separate
  "Digital Infrastructure" detected-sources panel and a saved-connections
  list. Portrait §24's marketplace is this screen widened to the full
  Capability catalog (not just `integrations/`) with a price-before-connect
  element and a "Рекомендации" section — not a new screen.
- **Results registry pattern**: `app/views/ResultsView.tsx` renders tabs
  from a backend registry (`api.results()` → id/label/icon/order/count)
  with per-tenant `ui_prefs` ordering — this is the established "registry
  becomes browsable UI" pattern (mirrors `results.py`/`artifact.py` on the
  backend); reuse it rather than inventing a second registry-to-UI pattern
  for the marketplace.
- **Onboarding**: `app/onboarding/OnboardingFlow.tsx` — 5 phases already:
  `chat` (live investigation dialog) → `analyzing` → `result` (analysis +
  growth points + initiative accept/reject) → `integrations` (reuses
  `IntegCard`) → `building` (avatar birth animation). ⚠️ Verify at
  implementation time whether a manual scenario picker (business/launch/
  idea) still exists as a distinct UI step before assuming portrait §23's
  "office determines shape itself" needs to remove one — it may already be
  chat-driven with no explicit picker; don't do speculative surgery.
- **The isometric scene**: `app/components/OfficeView.tsx`, 176 lines —
  genuinely simple: a CSS perspective-grid floor, 7 **hardcoded** `ROOMS`
  (percent-rects with Russian labels), ~27 hardcoded `DESKS`, a fixed
  `ROLE_HOME` map, agents as spring-animated emoji circles with a random
  6-second "meeting" toggle for liveliness. No true room-entry logic, no
  pathfinding. Confirmed weak, as portrait §9/§23 already noted — but
  portrait §10 (office visually grows with trust/autonomy) does **not**
  require the full scene rewrite that's deferred separately: it only needs
  `ROOMS` driven by `org.open_departments()` instead of hardcoded, and a
  discrete "stage" prop swapping floor/room styling. Do that narrow thing
  for 3.5 below; leave the bigger redesign (richer visual metaphor for
  non-web work, §9) as its own, separately-scoped future session.

---

## 1. What's already shipped (do not redo)

Two iterations landed already, both grounded in this same design work:

1. **Fact provenance/confidence** (`src/office/knowledge.py`) — `SOURCES`
   dict (measured/outcome/scanned/researched/owner_said/inferred → weight),
   `remember(..., source=)`, scan-derived GLOBAL facts, `remember_fact` tool
   (`src/agents/tool_schemas.py`, `src/agents/integration_tool_handlers.py`,
   `src/agents/agent_factory.py`). Test: `tests/test_knowledge_provenance.py`.
   Commit `269bc00`.
2. **Capability-neutrality in World Model** (`src/office/world.py`) —
   `results_summary` generic projection via `results.py`; `context_block()`
   no longer hardcodes "Сайты: X, лиды: Y". Commit `85fd7f0`.

Both are covered by `tests/run_all.py` (63/63 passing as of this writing).
Verify that's still true before starting new work — if it isn't, that's a
regression to fix first, not a reason to skip verification going forward.

---

## 2. How to work (non-negotiable, matches this repo's existing discipline)

- **One iteration at a time.** Pick ONE item from Section 3, implement it,
  verify it, commit it, write a handoff entry, stop. Do not chain multiple
  iterations in one session without a verification checkpoint between them —
  that's how the two shipped iterations were actually done, and it's why
  they're trustworthy.
- **Verify every iteration:**
  `python -m py_compile $(git ls-files '*.py')` · `cd webapp && npx tsc --noEmit`
  (only if you touched frontend) · `python tests/run_all.py` (must stay green;
  add a new `tests/test_<feature>.py` for anything with real logic, following
  the isolation pattern in `tests/test_processes.py` / `tests/test_knowledge_
  provenance.py`: `ctx.set_tenant(name); ctx.wipe(); ctx.set_tenant(name)`).
- **CQRS law is absolute** (`src/office/world.py` docstring): if a new UI
  surface needs a fact about the world, it's a new read in `world.snapshot()`
  or a new pure projection module — never a second place that independently
  re-derives something `world.py` already aggregates. Before adding ANY new
  persisted field, ask: can this be computed from what already exists? The
  portrait repeatedly favors projections over new state (office_stage,
  results_summary, causal-chain attribution) — follow that pattern.
- **Three layers, three places** (CLAUDE.md §4): domain logic only in
  `office/*.py`; HTTP only in `server.py`/`routers/*.py` (thin); persistence
  only through `context.read_json/write_json`. Don't blur these.
- **Update `docs/handoff.md`** after every shipped iteration — dated section,
  what changed, why, what broke and got fixed. This is how the next session
  (including future-you) knows what's real vs. planned.
- **Don't add the model name to commits/comments** (CLAUDE.md §5).
- Commits in Russian, small, matching existing history style. Only commit
  when explicitly asked, per standing tool instructions — but *this prompt*
  constitutes that ask for the specific iteration you're mid-way through
  finishing, not a blanket license to commit unrelated work.

---

## 3. Prioritized worklist

Ordered by two things: what unblocks the most other decisions, and what's
cheapest to verify in isolation. Pick from the top unless you have a good
reason not to — note that reason in the handoff entry if you skip ahead.

### 3.1 Risk as a learned Fact (portrait §5a, §13, §16-Q1, §21) — do this first

This is the fulcrum: menu-vs-autonomous decisions (§4), the three voice
intensities (§13), severe-mistake autonomy downgrade (§13), and the
untrusted-content barrier (§21) all read from this mechanism. Implementing
it once unblocks the rest instead of hardcoding partial versions of it four
times.

- Extend the Fact contract in `knowledge.py` (or a new small `risk.py` next
  to it — your call, but don't duplicate the SOURCES/confidence machinery
  that already exists) with a risk dimension: initial estimate is `inferred`
  (a reasoned guess — visibility × irreversibility × cost, portrait §6.2 of
  the canonical spec), and after a real outcome is observed it becomes an
  `outcome`-sourced fact with recalibrated confidence. This is Outcome
  Learning (canonical spec §6.5) applied to risk specifically, not a new
  learning loop — reuse the same provenance mechanism from iteration 1.
- Office evaluates risk itself, postfactum (portrait §16-Q1) — no
  provider-declared risk score, no platform pre-review of risk level.
- Wire this into `autonomy.py`: `needs_approval`/`can_auto` should
  eventually read learned risk instead of (or alongside) the static
  `_ACTION_MIN_LEVEL` table. Don't rip out the static table in this
  iteration — add the learned layer additively, prove it works, migrate
  callers later.
- Test: does a `Capability` that caused a bad outcome once show elevated
  risk on the next `needs_approval` check? That's the core behavior to prove.
- **Frontend (only once the backend shape is stable):** the three voice
  intensities (§13 — quiet / info-notification / blocking-confirmation)
  render through `RightPanel.tsx`'s existing feed machinery, not a new
  panel: quiet = ordinary feed entry (no change), info-notification = new
  `KIND_COLOR` entry + non-blocking feed item, blocking-confirmation = a
  feed item that also surfaces as a persistent unresolved card (check
  whether `ProjectView.tsx`'s initiative-card pattern is reusable here
  before inventing a new card type). Don't build this frontend piece before
  the backend risk mechanism actually emits distinguishable event kinds —
  there's nothing to render yet otherwise.

### 3.2 Untrusted-content architectural barrier (portrait §21)

Depends on 3.1 existing conceptually but is separately shippable and is a
real security gap right now: content read via `company_scan.py` (or any
future scan of a non-client-controlled URL — competitor sites, external
pages) must not be able to trigger a tool call directly. It should land as
a Fact for review, not get spliced into an agent's tool-loop context with
action capability. Find where `company_scan` output currently flows into
prompts (`prompt_builder.py`, `knowledge._scan_facts`) and add a boundary:
distinguish "scanned own site" (already lower-risk, portrait §7) from
"scanned third-party site" — the latter needs the hard barrier, not just a
lower confidence weight.

### 3.3 Severe mistake → autonomy downgrade (portrait §13)

Small, self-contained. `autonomy.py` has `upgrade()`; add symmetric
`downgrade(reason)`. Trigger: an action with high risk score (from 3.1) that
produced a bad outcome. Keep `trust.py`'s existing internal scoring
untouched — this is an *additional*, more visible consequence for the
subset of failures that clear the severity bar, not a replacement.
**Frontend:** the explicit acknowledgment (§5b — "признание ошибки, не
тихий trust.py-декремент") is a new `KIND_COLOR` kind in `RightPanel.tsx`'s
`FeedTab`, styled distinctly (this is meant to be noticed, not blend into
`system`/`speech`) — not a new component.

### 3.4 Growth/maintain toggle (portrait §11) — do NOT reuse `growth_style`

⚠️ The portrait is explicit that `philosophy.py`'s existing `growth_style:
"stable"` means "grow carefully," not "don't seek growth." This needs a
new, separate field (`boost: bool` or similar) that gates ONLY the office's
own autonomous entry into Gap Analysis / Understanding Gap as a *source* of
new Initiatives. Process-triggered and owner-triggered Initiative creation
must never be gated by this field — re-read portrait §11 before implementing,
it's easy to get this boundary wrong.

### 3.5 `office_stage` — pure projection, game-layer foundation (portrait §10)

Cheap, isolated, good "prove the pattern works" iteration. A read-only
function deriving a small discrete visual stage from numbers that already
exist (`trust.get_score()`, `autonomy.get_level()`, `len(org.
open_departments())`, `len(registry.all_agents())`) — zero new persisted
state for the stage itself. The one legitimate new state is a tiny dedup
marker for "this capability-unlock celebration has already played" (portrait
§10) — keep it that small, resist the urge to build more.
**Frontend — narrow, not the full scene redesign:** `OfficeView.tsx`'s
`ROOMS` array is currently hardcoded to 7 fixed rooms; drive it from
`org.open_departments()` (exposed via a new small field in whatever endpoint
already feeds this component — check `data/api.ts` for what `OfficeView`
currently fetches) instead, and add a `stage` prop that swaps a CSS
class/floor-texture tier. Do not attempt the richer "visual metaphor for
non-web work" redesign here — that's explicitly deferred in the portrait
(§9) as its own future session, and conflating the two will blow the scope
of this iteration.

### 3.6 Multi-user access (portrait §12) — bigger, do later, own epic

Three separately-grantable permissions (domain visibility / domain final-
decision authority / direct agent-directive rights), always granted only by
the founder, conflicts escalate to founder. Real new data model on top of
`saas/auth.py`. Also needs `intent.py`'s `source` field generalized beyond
`"owner"` to detect cross-user directive conflicts (portrait §12). Don't
start this until 3.1–3.5 are stable — it's a genuinely bigger lift and
touches auth, which deserves its own careful session.

### 3.7 Marketplace UI + provider manifest (portrait §24, canonical spec Part 14)

⚠️ **Not a new screen** — `app/views/ConnectionsView.tsx` already renders a
categorized catalog grid with `IntegCard` per provider (OAuth/API-key/
Telegram/Bitrix24 flows already built). This iteration is: (a) widen what
feeds that grid from `integrations/registry.py` alone to the unified
Capability catalog once it exists (skills + results-registry entries too,
not just `integrations/`), (b) add a price-before-connect element to
`IntegCard` for paid providers (portrait §24 — first-class, not fine print),
(c) add a "Рекомендации" section reading from wherever the office's
proposal-cards already live (same source `RightPanel`/`ProjectView` read
for initiative cards — don't build a second proposal queue). Backend side:
a manifest schema addition to `integrations/base.py`'s `Integration`
dataclass — a new field declaring which Fact-producing signals a provider
supplies (canonical spec §5.3). Do this after 3.1 exists, since "what risk
tier does this provider get" should already be answered by the learned-risk
mechanism, not invented separately here.

### 3.8 Onboarding flow (portrait §23)

Collapses the 3 manual scenarios into one adaptive entry (⚠️ verify first
whether `OnboardingFlow.tsx`'s `chat` phase already has no explicit picker —
see §0.5 frontend map note before assuming removal work is needed), adds a
draft/session state for pre-registration scans (so a test/wrong-URL scan
doesn't silently become permanent CWM data — likely a `sessionStorage`-only
draft until the flow reaches `integrations`/registration, mirroring how the
landing-page scan result already round-trips through `sessionStorage` per
the existing `analyzing`-phase code), and gates full BOOTSTRAP behind
explicit confirmation of the first dashboard (new UI state in the `result`
phase, or a new phase between `result` and whatever triggers BOOTSTRAP
today). Touches `routers/team.py`, `office/onboarding_result.py`,
`office/investigation.py`, and `OnboardingFlow.tsx`. Larger, cross-cutting —
do after the mechanisms it depends on (risk-gated confirmation from 3.1,
office_stage from 3.5 for the "office is thinking" visual) are in place.

---

## 4. Definition of done, per iteration

Not done until: code compiles/type-checks, `tests/run_all.py` is green
(63+ files), a new test exists for new logic, `docs/handoff.md` has a dated
entry naming what changed and why, and — if the iteration touches something
the canonical spec's Part 17 audit marked 🟡/❌/🔧 — that audit line gets
updated to reflect new reality (don't let the audit rot into fiction).

Stop and ask the user only for: anything genuinely undecided that isn't in
either doc's "Открытые вопросы" section already, or anything that would
touch the one hard invariant from portrait §14 (the ethical floor — no
change there ships without explicit confirmation, since by design it's the
one place no single session should quietly reinterpret).
