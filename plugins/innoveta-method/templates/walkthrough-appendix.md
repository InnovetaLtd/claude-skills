# Walkthrough appendix: <App name>

How innoveta-method's `walkthrough` skill runs in THIS app. The method lives in the plugin; this file only holds the
app's commands and locations. Save it as `docs/walkthrough-appendix.md`. Read every command from the app's own dev
docs: never guess one, since the skill runs them against a database.

| What | Where / how |
|---|---|
| The live SHA (start of the default range) | TODO: e.g. the `DEPLOY STATE` line in CLAUDE.md, or a `live` tag |
| What landed since (Fixed tables, rulings) | TODO: e.g. `docs/bug-intake-*.md`, `docs/rulings-*.md` |
| The walkthrough worktree | TODO: e.g. `git worktree add -b claude/walkthrough-<date> ../<app>-walkthrough-<date> origin/master` |
| A throwaway database | TODO: the command that builds a fresh one into a given folder, and how the server is pointed at it |
| The server | TODO: the start command, no auto-reload; how a free port is measured |
| Signing in as Ben locally | TODO: e.g. a dev-user environment variable |
| The ONE seed command | TODO: e.g. `manage.py seed_shapes <screen> <setup>` |
| Upload documents | TODO: the folder they go in, and what renders a realistic PDF |
| Phone-first screens | TODO: the screens that carry a "check on a phone" step |
| What cannot work locally | TODO: the cloud fetches, AI reads and sibling-app calls a check must name |
| The walkthrough doc | TODO: e.g. `docs/reviews/<date>-walkthrough.md` |
| Ledger, index, ideas board | TODO: where the one owed line, the index row and parked items go, and the not-yet-built marker |
| Tests and record checks | TODO: the full-suite command and the record checks run before landing |
| Landing path | TODO: how the walkthrough branch lands (e.g. a merge queue); never a deploy |

## This app's own rules a walkthrough must not break

- TODO: the standing rules worth a two-line interruption (e.g. "never add a delete path", an ADR boundary, frozen
  code identifiers).
