---
name: deploy
description: Ship a project to production safely — run the project's test suite, gate on CI, deploy, and verify live, reading the per-project commands/gates/gotchas from a `## Deploy` block in CLAUDE.md. Use when asked to "deploy", "ship", "push to prod", "release", "go live", or push a change to production. If the project has no `## Deploy` block yet, this skill STOPS and hands off to `deploy-init` to capture the process first — never improvise a production deploy.
---

# Deploy to production (config-driven)

A **live production deploy**. The per-project specifics — commands, gates, the health signal, gotchas — live in a **`## Deploy` block in `CLAUDE.md`**; this skill is the reusable discipline that runs them. Read that block first: it is the contract.

## Step 0 — Find the `## Deploy` block (gap-detection handoff)
Read `CLAUDE.md` for a `## Deploy` block.
- **If there is none, STOP — do not improvise a production deploy.** The process isn't captured, so there's nothing to gate against. Offer to run **`deploy-init`** to capture it first (the right move once deploys are understood and repeating). Only if the user *explicitly* wants a one-off manual deploy, ask them for the exact test / CI / deploy commands and proceed with the gates below — then recommend capturing it with `deploy-init` afterwards so the next one is repeatable.
- **If it exists,** it names: the prod target + health signal, the branch + remotes (deploy vs CI), the test command, the CI check, the deploy command, the safe-paths globs, the authorisation stance, where to record deploy state, and project-specific reminders. Use those values throughout — don't hardcode your own.

## Authorisation
If the block says that invoking this skill **is** the user's standing go-ahead to deploy, push **without** a separate "shall I deploy?" — but the **hard gates are non-negotiable**: never deploy on red tests or red CI. Invoking the skill authorises the push, not skipping the safety gates. If the block grants no standing authorisation, confirm before the production step.

## Step 1 — Know what's shipping
`git status`, and diff the deploy branch against the deploy target named in the block, so you can state exactly which commits this deploy carries. Surface anything unexpected. Don't deploy a half-finished tree silently — uncommitted changes that belong in the deploy get committed in Step 3.

## Step 2 — Tests must be green (abort if not)
Run the block's **test command**. If anything fails, **STOP** — diagnose, fix, re-run. Never deploy red. Honour any test caveats the block lists (e.g. "migrations/seeds must be idempotent across N workers").

## Step 3 — Commit only approved changes
Commit on the deploy branch using the project's commit conventions (co-author trailer if it uses one). **Classify the diff against the block's safe-paths:** a commit touching **only** docs/tests is a *safe update* — auto-deploy once green, no separate confirmation; anything touching **app code** needs explicit go-ahead first. When in doubt, treat it as app code and confirm.

## Step 4 — CI gate (abort if red)
Push to the **CI remote**; confirm green via the block's **CI check** before touching prod. CI on a clean runner catches what local runs mask. Red ⇒ STOP and fix.

## Step 5 — Deploy
State what's shipping + that CI is green for the record, then run the block's **deploy command**. Handle any known deploy quirk the block lists (e.g. a stale lock file → clear and retry).

## Step 6 — Verify the live deploy
Check the block's **health signal** — it tells you what "healthy" actually looks like (a specific status code, a clean build log, a recycle). Anything else means investigate, not "done". Note any expected-but-alarming behaviour the block flags (e.g. a slow first request after restart).

## Step 7 — Record deploy state
Update the deploy-state record where the block says (usually a line in `CLAUDE.md` and/or `PROJECT_STATUS.md`): what shipped, the deployed SHA, the CI run id. Keeping the branch/remote tips straight is part of done.

**Done = shipped AND verified live**, not merely pushed. Honour the block's **reminders** — especially anything that does *not* ride the deploy (data, migrations applied out-of-band, platform-specific steps).

## Pairs with
- **`deploy-init`** — writes the `## Deploy` block this skill reads. When the block is missing, route there first.
