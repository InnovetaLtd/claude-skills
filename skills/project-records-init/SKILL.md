---
name: project-records-init
description: Set up (or migrate a project onto) the tiered project-records doc system — a lean CLAUDE.md plus PROJECT_STATUS / ROADMAP / HISTORY, with a `## Project records` block that the session-wrap skill routes off. Use when starting a new project, when CLAUDE.md has bloated with session logs / long specs, or when the user says "set up project docs/records", "standardise the project docs", "scaffold CLAUDE.md + status/roadmap/history", or "initialise project memory".
---

# Project records — initialise

Stand up a project's documentation so context stays lean and handoffs survive cold starts. The system is **tiered by lifespan**: the always-loaded instruction file stays small, and everything ephemeral or bulky lives in referenced-not-loaded files. A short `## Project records` block in `CLAUDE.md` *declares* the structure so the `session-wrap` skill knows where to write.

## The architecture (four tiers, by lifespan)

| File | Holds | Lifespan / how it's edited |
|---|---|---|
| **`CLAUDE.md`** | Durable agent instruction: working prefs, build queue, architecture, gotchas, **roadmap index**, open issues. | Long-lived; loaded in full **every session** — keep it lean. |
| **`PROJECT_STATUS.md`** | Current snapshot: what's live, deploy state, test count, what's in progress / next. | Refreshed/overwritten as state changes. |
| **`ROADMAP.md`** | Backlog detail: full scope/design per numbered item. CLAUDE.md keeps only a one-line index. | Append/expand per item; grows with the backlog. |
| **`HISTORY.md`** | Append-only session log: "what shipped this session + why + files touched + commit/deploy". | Append newest-first; never rewritten. |

**Tier to the project's size — do NOT force four files on a project that hasn't earned them:**
- **Always:** `CLAUDE.md`.
- **Add `PROJECT_STATUS.md`** once there's ongoing state worth snapshotting.
- **Add `HISTORY.md`** once sessions start to accumulate (or from day one if you want the discipline).
- **Add `ROADMAP.md`** once there's a real backlog. An existing spec/concept doc (e.g. `CONCEPT.md`) can play the roadmap role — name it in the block rather than duplicating it.

A tiny utility might keep just `CLAUDE.md` (+ maybe `PROJECT_STATUS.md`). That's correct, not lazy.

## Steps

### 1. Assess the project
- Is there a `CLAUDE.md`? If **not**, suggest running the built-in **`/init`** first (it generates a CLAUDE.md from the codebase), then come back here to add the records architecture. This skill *complements* `/init`, it doesn't replace it.
- What already exists — a `PROJECT_STATUS.md` / `STATUS.md` / `CHANGELOG.md` / `CONCEPT.md` / a "Session status" block in CLAUDE.md? Reuse existing conventions; don't invent parallel ones.
- How mature is it (concept / early / shipping)? This sets the tier (above).

### 2. Agree the tier set
Propose the file set for this project's maturity and confirm with the user. Default for a non-trivial, shipping app: all four. For concept-stage: `CLAUDE.md` + `PROJECT_STATUS.md` (+ an existing `CONCEPT.md` as the spec/roadmap), add `HISTORY.md` when building starts.

### 3. Migrate existing content OUT of CLAUDE.md (if bloated)
If CLAUDE.md already holds session logs or long per-item specs, move them — **verbatim, nothing lost**:
- `## Session status` / dated session blocks → `HISTORY.md`.
- Long roadmap/feature specs → `ROADMAP.md`, leaving a one-line index per item in CLAUDE.md.
Split mechanically (by section header) and verify every original non-blank line still appears in one of the files before removing it from CLAUDE.md.

### 4. Create the files
Create only the chosen files that don't already exist, each with a short header and cross-pointers to the others (templates below).

### 5. Write the `## Project records` block into CLAUDE.md
Insert near the top (right after the H1 title). List exactly the files chosen and the routing rules (template below). This block is the contract `session-wrap` reads — if a file isn't part of this project, don't list it.

### 6. Confirm
Tell the user what was created/migrated, and that `session-wrap` will now route session-end updates to these files automatically.

## Templates

**`## Project records` block (put at the top of CLAUDE.md, adjust the file list to the tier set):**
```
## Project records — files, by lifespan (read this first)
Keep the docs tiered so **CLAUDE.md stays lean** — it is loaded in full at the start of every session.
- **`CLAUDE.md` (this file) — DURABLE instruction only.** Working prefs, build queue, architecture, gotchas, roadmap index, open issues. No per-session narrative, no deploy-state bookkeeping, no long specs.
- **`PROJECT_STATUS.md` — the CURRENT snapshot.** What's live, deploy state, test count, what's next. Refresh/overwrite as state changes.
- **`ROADMAP.md` — the BACKLOG detail.** Full scope/design per numbered item; CLAUDE.md carries only the one-line index.   ← omit if not used
- **`HISTORY.md` — the APPEND-ONLY session log.** What shipped each session + why + files + commit/deploy. Reference only.

**When wrapping a session:** append to `HISTORY.md`, refresh `PROJECT_STATUS.md`, update `ROADMAP.md` (+ the index) if scope changed, and touch the rest of `CLAUDE.md` only if a durable rule/decision changed. **git log** is the system of record for deploy state — don't re-narrate it in prose.
```

**`HISTORY.md` header:**
```
# <Project> — Session History (append-only log)

Detailed, append-only record of what shipped each session — the backstory behind the durable instructions in `CLAUDE.md`. Reference only; never loaded wholesale into context.

- Standing rules / architecture / roadmap index → `CLAUDE.md`
- Current snapshot → `PROJECT_STATUS.md`
- Canonical commit / deploy timeline → `git log`

Append new sessions at the top.

---
```

**`PROJECT_STATUS.md` header:**
```
# <Project> — Status at a Glance

*Human-readable snapshot of where the project is. Last updated: <date>.*

> Tiered docs: `CLAUDE.md` (durable) · `PROJECT_STATUS.md` (this, snapshot) · `ROADMAP.md` (backlog) · `HISTORY.md` (log).
```

**`ROADMAP.md` header:**
```
# <Project> — Roadmap (full detail)

Full scope/design per item — the backlog detail behind the one-line index in `CLAUDE.md`. Items are numbered; CLAUDE.md and the build queue reference these numbers.

---
```

## Pairs with
- **`session-wrap`** — maintains this structure at session end (reads the `## Project records` block to route updates). The two skills share that block as their contract.
