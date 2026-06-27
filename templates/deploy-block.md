<!--
  Paste this block into CLAUDE.md (near the deploy-related working preferences).
  It is the CONTRACT the `deploy` skill reads to run a gated production deploy.
  `deploy-init` writes it once the deploy process is understood; it is LIVING config —
  add gotchas as they surface. Replace every <bracket>; leave a TODO: marker for anything
  not yet known rather than guessing a value into a production-deploy contract.
-->

## Deploy — config for the /deploy skill
- **Prod target:** <platform>. Live: <URL>.
- **Branch / remotes:** `<branch>`; deploy → `<deploy-remote>`, CI → `<ci-remote>`.
- **Test gate (hard):** `<test command>` (~<time>). Red ⇒ STOP. <any caveat, e.g. idempotent seeds across N workers>
- **CI gate (hard):** `<push-to-CI command>` → `<check command>`; on red `<view-failure command>`. Do not deploy on red CI.
- **Deploy command:** `<production push>`. <known quirk + fix, e.g. on a stale lock file → clear and retry>
- **Authorisation:** <does invoking /deploy authorise the push, or confirm each time?> Hard gates (green tests + green CI) stay non-negotiable either way.
- **Safe-paths (docs/tests-only ⇒ auto-deploy once green, no separate confirm):** `<globs, e.g. *.md, tests/**>`. Anything else = app code ⇒ confirm first.
- **Verify live:** <what a healthy deploy looks like — a status code, a clean build log, a recycle>. <expected-but-alarming behaviour, e.g. slow first request>.
- **Record state:** update <where — e.g. the deploy-state line in CLAUDE.md / PROJECT_STATUS.md> with the deployed SHA, CI run id, and what shipped.
- **Reminders:** <anything that does NOT ride the deploy — data, out-of-band migrations, platform steps>.
