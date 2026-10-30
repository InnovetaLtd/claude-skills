# Innoveta Method

A Claude Code plugin packaging Innoveta's **operating system for AI-maintained codebases** — the documentation and session discipline that keeps a project's context lean, its handoffs cold-start-proof, and parallel work conflict-free.

*Part of the [Innoveta Claude Skills](../../README.md) marketplace. Install it into any project you maintain through Claude Code.*

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
  deploy/                 Gated production deploy, driven by a per-project `## Deploy` block
  deploy-init/            Capture an understood deploy process into that `## Deploy` block
  surface-review/         Goal-first review of a screen by an independent agent, recorded per screen
  surface-review-init/    Set an app up for it: registry, seed command, records, gate + lint wired in
standards/
  surface-review.md          THE surface review standard: goal, friction checklist, output, how it is enforced
scripts/
  check_surface_reviews.py   The gate (stdlib): refuses an unreviewed or unregistered screen
  surface_lint.py            The layout lint (Playwright): overflow, wrap, tap size, console, contrast, fold
templates/
  project-records-block.md   The `## Project records` contract block for CLAUDE.md
  PROJECT_STATUS.md / ROADMAP.md / HISTORY.md   Tier headers
  ideas-README.md / IDEAS_INBOX.md              The ideas convention + board
  deploy-block.md            The `## Deploy` contract block for CLAUDE.md
  working-preferences.md     Reusable Innoveta operating doctrines (edit per project)
```

### Surface review: the machines do the nitpicks

Every app with screens runs ONE review method (`standards/surface-review.md`): the job written once per screen, an independent fresh-agent reviewer, a severity scale and a stop rule, a mechanical layout lint, and a gate in the app's landing path that refuses a screen change nobody reviewed. Apps FETCH the scripts at a pinned commit (`plugin_ref` in their `surface-review.toml`), never copy them. Set an app up with `/surface-review-init`.

### Deploy is config-driven, not hardcoded

Deploy targets differ per project, so the `deploy` skill ships the reusable *discipline* — diff what's shipping, **hard-gate on green tests + green CI**, classify docs/tests-only (auto) vs app code (confirm), deploy, verify live, record state — and reads the per-project *knobs* (commands, health signal, gotchas) from a **`## Deploy` block in `CLAUDE.md`**. That's the "in-app config over hardcoding" doctrine applied to the toolkit itself: specifics live in data, not code.

`deploy-init` writes that block once the deploy is **understood and repeating** (after the first one or few manual deploys — not on day one, when the gotchas aren't known yet). And `deploy` does **gap-detection**: if a project has no `## Deploy` block, it stops and routes to `deploy-init` rather than improvising a production push — so the high-frequency "deploy" trigger reliably pulls in the harder-to-time setup step.

## Install

This plugin ships from the `innoveta` marketplace at [`InnovetaLtd/claude-skills`](https://github.com/InnovetaLtd/claude-skills). Wire a project to it with that repo's `scripts/enable-in-repo` script (see the [root README](../../README.md)), or by hand in an interactive `claude` terminal:

```
/plugin marketplace add InnovetaLtd/claude-skills
/plugin install innoveta-method@innoveta
```

The six skills then become available: invoke them with `/project-records-init`, `/session-wrap`, `/ideas`, `/ideas-triage`, `/deploy`, `/deploy-init`, or let the agent trigger them from their descriptions.

## Use, per project

1. **New project:** run `/project-records-init` — it assesses maturity, proposes a tier set, creates the files, and writes the `## Project records` block. (Run the built-in `/init` first if there's no `CLAUDE.md` yet.)
2. **As you work:** when context gets long or you're about to start fresh, run `/session-wrap` — it updates the records and confirms they're current before recommending a restart.
3. **Thinking, not building:** start a second session and run `/ideas` to capture ideas safely alongside live coding. Later, in the coding session, run `/ideas-triage` to fold them into the roadmap/queue.
4. **Once deploys are routine:** run `/deploy-init` to capture the process into a `## Deploy` block, then ship with `/deploy` (tests → CI → deploy → verify, with the safe-vs-app-code rule). Until that block exists, `/deploy` will route you to `/deploy-init` first.

## Status

`v0.3.0` — the surface review (standard, two skills, gate + lint scripts) is new; the four records/ideas skills are production-proven; `deploy` + `deploy-init` are new (config-driven, gap-detection handoff); templates and this README are first-draft. Triggering relies on each skill's description (model-invoked — no manual call required), with the high-frequency `deploy` skill routing into the harder-to-time `deploy-init`. A deterministic hooks layer (fire on an actual `git push`) is a possible future add only where a missed trigger would be costly.
