---
name: session-wrap
description: Produce a clean end-of-session handoff so the next session starts with full context. Use when the user says "wrap up", "let's wrap", "end of session", "update CLAUDE.md / the status doc", "summarize outstanding work", "I'm about to /clear or start fresh", or whenever you are about to recommend a fresh session because the context is getting long or usage-heavy. Brings the project's persistent status record fully up to date (what shipped, decisions + why, outstanding/next work, deploy state) and explicitly confirms it is current BEFORE suggesting a restart.
---

# Session wrap

Close out a working session by leaving a handoff the next (cold) session can pick up from. The next session sees **only** what you write down — not this conversation — so the status record is the single source of truth. Get it complete and honest before suggesting a restart.

**Golden rule:** never recommend starting fresh until the status record is updated AND you have explicitly told the user it is current. (When you suggest wrapping up *because* context is long, the update comes first, the suggestion second.)

## Steps

### 1. Take stock of the session
Reconstruct what actually happened — don't rely on memory of the conversation, ground it in the repo:
- `git status` and `git log` (since the session started) to separate **shipped/committed** from **only-in-the-working-tree** from **deployed** (if this project deploys, "committed" ≠ "live").
- What was built or changed, and what was *decided* (with the **why** — decisions without rationale rot fast).
- What is outstanding, half-done, blocked, or explicitly deferred. Be honest: if tests failed, a step was skipped, or something is unverified, say so plainly.

### 2. Find where this project records state
**First, check `CLAUDE.md` for a `## Project records` block** — a short section (usually near the top) that declares which files the project keeps and what goes where. If it exists, it is the contract; route each kind of update to the file it names:
- **session log / "what shipped this session" detail** → the history/log file it names (e.g. `HISTORY.md`). *Append* a new entry (newest first) — don't rewrite old ones.
- **current snapshot** (what's live, deploy state, what's next) → the status file (e.g. `PROJECT_STATUS.md`). *Refresh/overwrite* it.
- **backlog / scope changes** → the roadmap/spec file (e.g. `ROADMAP.md` or a `CONCEPT.md`) plus its one-line index in `CLAUDE.md`.
- **durable rules/decisions only** → `CLAUDE.md` itself.

When a records block exists, **do not paste session logs or deploy bookkeeping into `CLAUDE.md`** — keeping that file lean is exactly what the block is for (it's loaded in full every session).

**If there's no `## Project records` block,** fall back to the project's existing convention, in order:
1. a "Session status" / "Current status" section in `CLAUDE.md` (common in older projects);
2. a dedicated status doc — `PROJECT_STATUS.md`, `STATUS.md`, `CHANGELOG.md`, `NOTES.md`;
3. the session **memory** files (`MEMORY.md` index + memory dir).

If there's genuinely no convention, ask the user where to record it — or offer to set one up with the **`project-records-init`** skill — rather than guessing.

### 3. Update it
Record, specifically enough for a cold start:
- **What shipped this session** — and its real state (committed? merged? deployed/live? verified how?).
- **Decisions made** — each with its rationale.
- **Outstanding / next work** — what to pick up, and any known blockers.
- **Deploy state** — if the project deploys, what's live vs. what's only committed (this is where stale handoffs hurt most).

Rules:
- **Convert relative dates to absolute.** "today" / "yesterday" / "this week" → real dates. The next session won't know when "today" was.
- **Refresh the snapshot in place; append to the log.** In a *status/snapshot* doc, edit the existing entry and remove items now done — don't append a near-duplicate block. In an *append-only history/log* doc, add a fresh dated entry at the top and leave older ones untouched.
- **Match the existing format.** Mirror the section style, dating convention, and level of detail already in the doc.
- **Don't restate what the repo already records** (code structure, git history). Capture the *non-obvious*: intent, decisions, what's deliberately deferred and why.

### 4. Confirm, then suggest the restart
Only after the record is current:
- Tell the user **explicitly that the status record is now up to date.**
- Give a short summary of outstanding work.
- Then suggest the fresh session (e.g. `/clear` or a new session). Not before.

## Why this matters
A handoff that's optimistic, vague, or stale is worse than none — it sends the next session in confident and wrong (e.g. "deployed" when it's only committed). Accuracy over tidiness: report what's actually true, including failures and unfinished work.
