---
name: ideas-triage
description: Triage captured ideas — read the project's ideas/ capture files and promote each idea into the roadmap/queue, park it, or drop it, then log it on the ideas inbox board and clear the processed capture files. Use when the user says "triage the ideas", "process the ideas inbox", "promote ideas to the roadmap", "clear the ideas backlog", or after a run of /ideas discussion sessions. Run only in the coding/main session, never while a parallel discussion session is live.
---

# Ideas triage (the coding-session counterpart to `/ideas`)

This is the **triage half** of the parallel-safe ideas system. The `/ideas` skill *captures* ideas into dated files under `ideas/` and never touches the shared records. This skill does the opposite: it **reads those capture files and writes the durable records** (roadmap, queue, inbox board). The two skills have **disjoint write lanes**, which is what lets a discussion session and a coding session run at the same time without colliding.

## The one hard rule — your write lane (the mirror of `/ideas`)
- **Only run this when NO discussion/ideas session is live.** Triage writes the inbox board + roadmap + queue; a discussion session writes the capture files. If both run at once the disjoint-lane guarantee breaks. If you suspect a discussion session is active (recent un-triaged capture files still being appended, the user mentions a second session), confirm with the user before writing.
- You write to the **shared records** — the roadmap, the `CLAUDE.md` queue + roadmap index, the ideas inbox/board — and you **clear** processed capture files. You do **not** invent new ideas here; you only process what was captured.

## Find the project's ideas convention first
Mirror `/ideas`'s discovery so you operate on the right files:
1. Read `CLAUDE.md` for the ideas/discussion-flow description (often inside a `## Project records` block) — it names the directory, the inbox/board file, and the idea-block format.
2. Locate: the **capture directory** (usually `ideas/`), its `README.md` (the format spec), the **inbox/board** file (e.g. `IDEAS_INBOX.md`), the **roadmap** (e.g. `ROADMAP.md`), and the **queue + roadmap index** (usually in `CLAUDE.md`).
3. If the project has **no** ideas convention, there is nothing to triage — tell the user and stop. (Setting one up is the `project-records-init` skill's job, not this one.)

## Procedure
Work through it in order; keep the user informed of the verdict per idea.

### 1. Gather the captures
- List every capture file in the ideas directory **except `README.md`**. Read them all.
- Read the inbox/board (current Pending / Parked / Triaged-log state), the roadmap, and the `CLAUDE.md` queue + roadmap index — so you place each idea correctly and don't duplicate an existing item.
- Each capture file holds one or more `## idea:` blocks. Triage **per block**, not per file (a file can mix a promote, a park, and an already-done).

### 2. Decide a verdict for each idea block
Pick exactly one:
- **Promote** — it's worth doing. Either **expand an existing roadmap item** (append a dated `TRIAGED …` note with the scope/decision/dependency) or **add a new numbered roadmap item** (next free number). If it's *scoped + agreed with no open questions*, also add it to the **build queue** in `CLAUDE.md` (in the right track — see the project's queue/track rules); if it still needs a scoping round or a dependency from the user, promote it to the roadmap but **park it** rather than queueing.
- **Park** — keep it, but deliberately not scheduled (needs scoping, blocked on an external dependency, cross-app decision). Record it under the board's **Parked / someday** section with the one-line reason, and add a roadmap item/note so the detail survives.
- **Drop** — not doing it. Record why in the Triaged log so it isn't re-litigated.
- **Already done** — the idea was overtaken by shipped work. Note it as shipped (with the commit/item) in the Triaged log; no roadmap change needed.

Apply the project's judgement rules from `CLAUDE.md` (e.g. queue tracks, "scoped + agreed" bar, in-app-config principles). When a verdict is genuinely the user's call (real priority or scope decision you can't resolve from the records), ask — but decide the clear-cut ones yourself and report them.

### 3. Write the durable records
- **Roadmap:** add the new item or append the `TRIAGED <date> (from ideas/<file>): …` note to the existing item — include the reasoning + any dependency, so the build picks up cold.
- **`CLAUDE.md`:** add a one-line entry to the **roadmap index** for any new item; add scoped+agreed ideas to the **build queue** in the correct track. Keep `CLAUDE.md` lean — detail lives in the roadmap, one-liners here.
- **Inbox board:** clear **Pending triage** to none; fill **Parked / someday**; append one **Triaged log** line per processed idea (`date · idea · where it went`).

### 4. Clear the processed capture files
- Once **every** block in a capture file has a verdict and is logged, **delete that file** (the inbox Triaged log + roadmap are now the durable record; git history keeps the original). Use `git rm` for tracked files and a plain delete for untracked ones — do them separately so one missing pathspec doesn't abort the whole removal.
- Leave the directory's `README.md` in place. If some blocks in a file remain undecided (you asked the user and are waiting), keep that file and flip only the decided blocks' `status:` to `triaged → ROADMAP #NN`.

### 5. Commit
- Triage touches **docs only** (roadmap, `CLAUDE.md`, the board, deleted capture files) — no app code — so per the project's safe-update rule it's an auto-deployable/commit-safe change. Commit on the working branch with a clear message (e.g. `Docs: triage ideas inbox → ROADMAP/queue (N ideas)`), following the project's commit conventions (co-author trailer, etc.).
- Report the verdicts to the user: what got promoted (and where), what was parked, what was dropped or already shipped.
