<!--
  Paste this block near the top of CLAUDE.md (right after the H1 title).
  It is the CONTRACT the session-wrap and ideas-triage skills read to route updates.
  Delete any tier you are not using (e.g. drop ROADMAP.md for a small project).
  Delete the "Parallel ideas" paragraph if you are not using the ideas workflow.
-->

## Project records — files, by lifespan (read this first)
Keep the docs tiered so **CLAUDE.md stays lean** — it is loaded in full at the start of every session, so anything dead-weight here is paid for on every turn.
- **`CLAUDE.md` (this file) — DURABLE instruction only.** Working preferences, the build queue, architecture, the data model, deploy process, gotchas, the roadmap **index**, and open/unresolved issues. Anything a future session needs as standing context. No per-session narrative, no deploy-state bookkeeping, no long per-item specs.
- **`PROJECT_STATUS.md` — the CURRENT snapshot.** Human-readable "where are we right now": what's live, current deploy state, test count, what's in progress, what's next / blocked. **Refresh/overwrite** it as state changes — it is a snapshot, not a log.
- **`ROADMAP.md` — the BACKLOG detail.** Full scope, design decisions and sub-status for every numbered roadmap item. CLAUDE.md carries only the one-line index; the detail lives here.   ← omit if not used
- **`HISTORY.md` — the APPEND-ONLY session log.** The detailed "what shipped this session + why + files touched + commit/deploy record" entries. **Reference only** — read it for backstory; never load it wholesale into context.

**Parallel discussion ("ideas") sessions — stay out of the shared records.** To talk through ideas in a *second* session running alongside a live coding session **without both editing `CLAUDE.md` at once**, use the **`/ideas` skill**. An ideas session writes to **exactly one dated file under `ideas/`** and must NOT edit `CLAUDE.md`, `PROJECT_STATUS.md`, `HISTORY.md`, `ROADMAP.md`, `IDEAS_INBOX.md`, or app code. Captured ideas are later **triaged** (in the coding session, when no discussion session is live) via the **`/ideas-triage` skill** into `ROADMAP.md` + the queue, logged on the `IDEAS_INBOX.md` board, and the processed capture files cleared. Disjoint writers ⇒ the two sessions never conflict.

**When wrapping a session:** append this session's detail to `HISTORY.md`, refresh `PROJECT_STATUS.md` to the new current state, update `ROADMAP.md` (+ the CLAUDE.md index) if scope changed, and touch the rest of `CLAUDE.md` **only** if a durable rule/decision changed. Do **not** paste session logs or deploy bookkeeping into `CLAUDE.md`; **git log** is the system of record for commit/deploy state — don't re-narrate it in prose. (The `session-wrap` skill does this.)
