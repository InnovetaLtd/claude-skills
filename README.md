# Innoveta Method

A Claude Code plugin packaging Innoveta's **operating system for AI-maintained codebases** — the documentation and session discipline that keeps a project's context lean, its handoffs cold-start-proof, and parallel work conflict-free.

*Private internal toolkit. Install it into any project you maintain through Claude Code.*

---

## Why this exists

When a codebase is maintained by an AI agent across many short-lived sessions, the binding constraint isn't compute or file size — it's **context and continuity**. Each session starts cold: it sees only what was written down, not the conversation that produced it. Two failure modes follow:

1. **`CLAUDE.md` bloat.** Everything important gets dumped into the one file that's loaded every session, until it's thousands of lines and every turn pays for dead weight.
2. **Lossy handoffs.** A session ends, the next one starts blind, and re-derives (or contradicts) decisions already made — worst of all, it trusts a stale "deployed" when something was only committed.

This plugin encodes the fixes as **skills the agent invokes automatically**, plus templates to scaffold a new project in one pass.

## The three core ideas

**1. Tier documents by lifespan.** Don't keep one big file — keep four, each with a different write rhythm:

| File | Holds | Rhythm |
|---|---|---|
| `CLAUDE.md` | Durable instruction: working prefs, build queue, architecture, gotchas, roadmap **index** | Loaded every session — kept lean on purpose |
| `PROJECT_STATUS.md` | The current snapshot: what's live, deploy state, what's next | Refreshed/overwritten in place |
| `ROADMAP.md` | Full scope/design per numbered item | Appended/expanded per item |
| `HISTORY.md` | Append-only "what shipped + why + files + deploy" log | Newest entry on top, never rewritten |

A short `## Project records` block at the top of `CLAUDE.md` *declares* which tiers a project uses — that block is the **contract** the skills route off. Tier to the project's size; a small utility might keep only `CLAUDE.md`.

**2. Make handoffs cold-start-proof.** Before any session that's about to end (or be `/clear`ed), bring the records fully current — grounded in `git`, not memory — and **explicitly confirm they're current before suggesting a restart**. Accuracy over tidiness: report what's actually true, including failures, unverified steps, and "committed but not deployed".

**3. Separate write lanes so sessions never collide.** You can run a second "ideas / discussion" session *alongside* a live coding session, because they write to **disjoint files**: the discussion session only appends to a dated capture file under `ideas/`; triage only writes the durable records — and only in the coding session, when no discussion session is live. Two non-overlapping write lanes ⇒ zero edit conflicts on `CLAUDE.md`.

The throughline: **the bottleneck is review bandwidth and continuity, not file size or compute.** Every convention here optimises for that.

## What's in the box

```
skills/
  project-records-init/   Scaffold or migrate a project onto the tiered docs
  session-wrap/           Cold-start-proof end-of-session handoff
  ideas/                  Parallel-safe idea capture (one dated file, no shared edits)
  ideas-triage/           Promote/park/drop captured ideas into the records
templates/
  project-records-block.md   The `## Project records` contract block for CLAUDE.md
  PROJECT_STATUS.md / ROADMAP.md / HISTORY.md   Tier headers
  ideas-README.md / IDEAS_INBOX.md              The ideas convention + board
  working-preferences.md     Reusable Innoveta operating doctrines (edit per project)
```

## Install

This is a plugin in a git repo. On any machine, add it as a plugin marketplace and install (run these in an interactive `claude` terminal):

```
/plugin marketplace add C:\dev\innoveta-method      # or the git URL once pushed
/plugin install innoveta-method@innoveta-method
```

The four skills then become available in every project on that machine — invoke them with `/project-records-init`, `/session-wrap`, `/ideas`, `/ideas-triage`, or let the agent trigger them from their descriptions.

## Use, per project

1. **New project:** run `/project-records-init` — it assesses maturity, proposes a tier set, creates the files, and writes the `## Project records` block. (Run the built-in `/init` first if there's no `CLAUDE.md` yet.)
2. **As you work:** when context gets long or you're about to start fresh, run `/session-wrap` — it updates the records and confirms they're current before recommending a restart.
3. **Thinking, not building:** start a second session and run `/ideas` to capture ideas safely alongside live coding. Later, in the coding session, run `/ideas-triage` to fold them into the roadmap/queue.

## Status

`v0.1.0` — the four skills are production-proven; templates and this README are first-draft. Planned next: a `deploy-init` skill that scaffolds a project's own test-gate → CI-gate → ship skill from a template (deploy targets are project-specific, so the deploy skill itself stays per-project).
