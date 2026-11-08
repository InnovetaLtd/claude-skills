# Walkthrough appendix: <App name>

How innoveta-method's `walkthrough` skill runs in THIS app. The method lives in the plugin, and how to prepare,
seed and serve the app lives ONCE, in `surface-review.toml` (the walkthrough records through the same engine).
This file holds only what a walkthrough needs beyond that. Save it as `docs/walkthrough-appendix.md`. Read every
command from the app's own dev docs: never guess one, since the skill runs them against a database.

| What | Where / how |
|---|---|
| The live SHA (start of the default range) | TODO: e.g. the `DEPLOY STATE` line in CLAUDE.md, or a `live` tag |
| What landed since (Fixed tables, rulings) | TODO: e.g. `docs/bug-intake-*.md`, `docs/rulings-*.md` |
| Running the plugin's scripts | TODO: how this app runs `surface_record.py` and `review_report.py` at its pinned `plugin_ref` (e.g. its wrapper's `record` / `report`), and the Python that has Playwright |
| A desk server Ben can drive | TODO: a seeded throwaway database and the serve command (usually the `[lint]` commands by hand), a measured free port, the dev-user sign-in |
| Upload documents | TODO: the folder they go in, and what renders a realistic PDF |
| What cannot work locally | TODO: the cloud fetches, AI reads and sibling-app calls a check must name |
| The walkthrough doc | TODO: e.g. `docs/reviews/<date>-walkthrough.md` |
| Ledger, index, ideas board | TODO: where the one owed line, the index row and parked items go, and the not-yet-built marker |
| Tests and record checks | TODO: the full-suite command and the record checks run before landing |
| Landing path | TODO: how the walkthrough branch lands (e.g. a merge queue); never a deploy |

## This app's own rules a walkthrough must not break

- TODO: the standing rules worth a two-line interruption (e.g. "never add a delete path", an ADR boundary, frozen
  code identifiers).
