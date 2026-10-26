---
name: deploy-init
description: Capture a project's understood, repeating deploy process into a `## Deploy` block in CLAUDE.md, so the `deploy` skill can run it with test + CI hard-gates and the safe-vs-app-code rule. Use once deploys are stable and understood (typically after the first one or few manual deploys) and there is no `## Deploy` block yet; when a manual deploy just happened with no /deploy config; or when asked to "set up deploy", "automate the deploy", "make deploys repeatable", or "capture the deploy process". NOT for the very first exploratory deploy — there is nothing reliable to capture yet.
---

# Deploy — capture the process (write the `## Deploy` block)

Turn an understood, repeating deploy into config the **`deploy`** skill can run with hard gates. The output is a `## Deploy` block in `CLAUDE.md` — durable instruction, so it belongs in the always-loaded file (next to the deploy-related working preferences).

## When to run (timing matters)
Run this once the deploy is **understood and stable** — typically after the first one or few deploys, when the next deploy would be *boring* (same steps, no surprises). The knobs worth capturing — especially what "healthy" looks like, lock-file quirks, and what does *not* ride the deploy — are usually **learned from doing it**, not knowable upfront.
- **Pre-first-deploy:** don't run this — there's nothing reliable to capture. Do the first deploy(s) by hand (have the agent note the commands and surprises as it goes), then come back.
- **Already has a `## Deploy` block:** this is an *update*, not a fresh write — edit the existing block (e.g. add a newly-learned gotcha) rather than duplicating it. The block is **living config** that accretes over time.

## Steps

### 1. Pre-fill the mechanical knobs from git
Read these — don't interview for them:
- `git branch --show-current` → the deploy branch.
- `git remote -v` → identify the deploy remote and (if separate) the CI remote.

### 2. Interview for the judgment parts
These aren't inferable — ask the user:
- **Test command** + roughly how long it takes; any caveat (e.g. "seeds/migrations must be idempotent across N workers").
- **CI check** — the command that confirms CI is green, and how to read a failure.
- **Deploy command** — the exact production push, plus any known quirk (a stale lock file, a slow first request after restart).
- **Prod target + health signal** — the live URL and *what a healthy deploy looks like* (a specific status code, a clean build log, a recycle). This is the most-missed knob — pin it explicitly.
- **Safe-paths** — which path globs are docs/tests-only (⇒ auto-deploy once green) vs app code (⇒ confirm first).
- **Authorisation stance** — does invoking `/deploy` count as standing go-ahead to push prod, or should it confirm each time?
- **Record-state location** — where the deployed SHA / CI run id is logged (a `CLAUDE.md` line, `PROJECT_STATUS.md`).
- **Reminders / gotchas learned so far** — anything that bites (data/migrations that don't deploy, concurrency-seed hazards, platform quirks).

### 3. Write the `## Deploy` block into CLAUDE.md
Place it near the deploy-related working preferences. Use the template in `templates/deploy-block.md`. Fill every field you have; for anything still genuinely unknown, leave a clear `TODO:` marker rather than guessing a value into a production-deploy contract.

### 4. Confirm
Tell the user the block is written and that `/deploy` will now read it and run the gated process (tests → CI → deploy → verify) with the authorisation stance recorded. Remind them it is **living config** — add new gotchas as they surface, and edit it when the deploy process changes.

## Pairs with
- **`deploy`** — reads the `## Deploy` block this skill writes, and routes here when the block is missing.
- **`project-records-init`** — if the project has no `CLAUDE.md`/records yet, set those up first; the `## Deploy` block lives in `CLAUDE.md`.
