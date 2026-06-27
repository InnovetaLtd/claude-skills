<!--
  Starter `## Working preferences` block for CLAUDE.md.
  These are Innoveta's reusable operating doctrines. Keep the ones that apply,
  delete the rest, and replace the <bracketed> bits with project specifics.
  Every preference should carry its WHY — a rule without a rationale rots fast.
-->

## Working preferences

- **In-app config over hardcoding (standing principle).** Maximise the flexibility to edit configuration, permissions and roles **from within the app** rather than hardcoding values or requiring a portal/redeploy — unless a change genuinely must live elsewhere for security reasons. Default new "who can do X" / "tune Y" settings to **DB-backed + an admin-only editor screen**; keep an env var / constant only as the initial default/fallback the in-app setting overrides. Genuine security exceptions (secrets, auth) stay out of the app — and say so explicitly when they do.

- **Deploy from the session, with the right gate.** <Describe the deploy command/target.> Confirm before deploying **app code** (each deploy is live). **Auto-deploy SAFE updates without asking:** a commit touching **only** docs and/or tests cannot change production behaviour, so once the test suite is green and CI passes, ship it without a separate confirmation. Any change touching app code still needs explicit go-ahead. When in doubt, treat it as app code and confirm.

- **Capture the deploy process once it's repeatable (`deploy-init`).** When a project starts deploying and has no `## Deploy` block in CLAUDE.md yet, wire one up via `deploy-init` before deploying becomes routine — so every deploy thereafter runs through `/deploy` with the test + CI hard-gates and the safe-vs-app-code rule, instead of ad-hoc. Don't do it pre-first-deploy (nothing reliable to capture yet); do it once the deploy is understood and the next one would be boring. The block is living config — add gotchas as they surface.

- **Fan out parallel subagents for read-only work, without asking.** For zero-conflict, read-heavy work — codebase research, multi-file audits, spec-writing, independent investigations — proactively launch parallel agents to move faster. **Keep BUILDS that edit shared files serial** (at most one feature build at a time on a shared module) to avoid merge conflicts. Don't ask permission to parallelise read-only work; do ask before spinning up many build agents (cost + review load).

- **Batch small changes; serialise big ones (the throughput model).** Organise the build queue into tracks:
  - **Track A — big serial builds** that hammer shared files: run **one at a time** (the bottleneck is review bandwidth + merge-conflict risk, not file size).
  - **Track B — medium builds** that touch shared files but are contained: slot one between Track A builds.
  - **Track C — small / isolated / new-file wins:** **batch several into ONE session → ONE test run → ONE deploy** rather than one-off pushes.
  - Sequence + batch to maximise value shipped per review/deploy cycle, not merely to clear items.

- **Optimise the codebase for AI maintenance, not human-team hygiene.** <If applicable:> large single files are fine — navigation is grep/offset, so file size is ~free; the real bottleneck is logical coupling + review bandwidth. **Do** flag and offer a module extraction when a genuinely self-contained unit emerges (extract as you build the feature, so the boundary is earned, not imposed). Surface the opportunity rather than silently refactoring.

- **Wrap up before context gets heavy.** When the conversation is getting long/usage-heavy, bring the records up to date (`session-wrap`) and confirm they're current **before** recommending a fresh session.
