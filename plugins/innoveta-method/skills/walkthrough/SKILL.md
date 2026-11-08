---
name: walkthrough
description: Ben's final review pass over what was built in an Innoveta app. Claude records every changed screen's flows (before and after), gathers what the build's own reviews found, and publishes one checklist artifact Ben can eyeball from a desk or a phone; at a desk he can also walk the work on a seeded dev server. His numbered feedback lands on each card as he gives it ("Noted — slice: …"), trivial bugs are fixed live, and at "review complete" every finding is grouped into six slices, ruled there and then, written into each screen's record with the layer that should have caught it, and handed off in a walkthrough doc a fresh session can pick up cold. Use when Ben says "walkthrough", "let me review what's built", "show me what's new", or after an integration lands and before /deploy. NOT a critique of one screen during a build (surface-review), NOT a bug-report pass, NOT a deploy gate.
---

# Walkthrough: Ben's final eyeball over everything the build produced

**Why this exists.** The build reviews itself (the `surface-review` skill: lint, recorded flows, an independent
reviewer, a gate on every merge). The walkthrough is the last pass, Ben's, and it is cheap for him: one artifact,
every change pictured with its before, what the reviewers already found and fixed, and what is left for him.
**Its second job is to teach the method:** every finding he makes is recorded with the layer that should have
caught it, so the leaks are counted (`scripts/review_report.py`) and repeats are promoted until fewer reach him.
Designed with Ben in Build Manager (2026-10-23; one pipeline with surface review since 2026-11-08).

**The engine is the surface review's** (`standards/surface-review.md` §4): the app's `surface-review.toml` says how
to prepare, seed and serve; its registry holds each screen's goal and flows; its records hold every finding. The
app's **walkthrough appendix** (`docs/walkthrough-appendix.md`; template `templates/walkthrough-appendix.md`)
adds only what a walkthrough needs beyond that: where the live SHA is, where intake and rulings docs live, the
upload folder, the walkthrough doc's location, the landing path. **No `surface-review.toml` ⇒ run
`surface-review-init` first; no appendix ⇒ offer to write one.** Never guess a command into a database.

## 1. Scope: what changed

**Default: everything merged to master since the last deploy** (the live SHA: appendix). Read:
- `git log <live>..origin/master --merges`: the PR titles, and each PR's body for its activator;
- the *Fixed* tables of every bug-intake and rulings doc written since then;
- every scope doc whose slices landed: **its scenarios are flows**, already registered on their screens.

**Argument:** a PR number, a doc, or a branch narrows it.

**The screens:** those the range touched (`surface_record.py record --changed-since <live>` selects them as the
lint does; if that falls back to every screen, narrow it with `--screens` to the ones the PRs name). **One check
per user-visible change**; a check shows the walks of the screens it is about. Tooling, docs and tests get none.

## 2. Record (all before Ben sees anything)

1. **After:** `surface_record.py record --app . --changed-since <live> --stills --out <scratchpad>/after`. Every
   registered flow on those screens, plus a desk and a phone picture of each screen's typical setup. For a
   change that has no flow yet (a bug fix), add a one-off walk with `--plan` (the docstring has the shape),
   seeded through the app's ONE seed command; where no setup shows it, **add the setup to that command**,
   copying the fix's own regression test, so the next walkthrough and the next review have it too.
2. **Before:** a worktree of the live SHA, then `record --app <that worktree> --same-as <scratchpad>/after/manifest.json
   --label before --out <scratchpad>/before`. A scenario the change adds is not on the base: its walk shows *new*.
3. **A walk that stopped is a finding** (its last picture shows where and why). Fix the walk if the walk was wrong;
   otherwise it heads the checklist as finding #0, with any 375 px or dark-mode failure the lint reports for
   these screens (`surface_lint.py --changed-since <live>`).
4. **What the build already found:** for each screen, the findings in its record since the live SHA, with their
   outcomes. They go on the card, folded: Ben sees what was caught without re-reading it.
5. **What pictures cannot judge** (*feel*: a fiddly field, a drag, a tap, the camera) is marked `desk_only`: *walk
   at a desk later*. The walkthrough doc lists every one as an owed desk check, so none is passed quietly.
6. **Things that cannot work locally** (a cloud fetch, a real AI read, a sibling app) are named in the check's
   *What you should see*, so a local failure is never mistaken for a bug.
7. **Upload documents** a check needs are generated into the appendix's upload folder, named after their record.
   **Ben never drafts a test document** (his words, 2026-10-23).

## 3. The checklist artifact

Write `walk.json` (title, date, range, mode, server, finding #0, and per check: n · title · ids · the data shapes
that matter · where · see · `walks` · `findings` · `desk_only`), then:
1. `surface_record.py mark --after <after> --before <before>`: finds what visibly changed (rows aligned like a
   text diff, so an insertion never lights up the page below it), keeps the boxes as coordinates, and writes the
   clean `.jpg` each picture is uploaded as.
2. `surface_record.py page --walk walk.json --after <after>/manifest.json --before <before>/manifest.json --out
   <scratchpad>/walkthrough-<date>.html`, and **publish** it with `capabilities: {db: {}, assets: {}}` (the
   `artifact-capabilities` skill holds the call shapes).
3. **Upload the `.jpg` views** (`asset: true`, up to 25 per call), write `{view: url}` to `urls.json`, rebuild with
   `--assets urls.json`, and republish the same file.
4. **Send Ben the link** in one line. Before and after sit side by side, what changed is boxed on both as a layer
   (the *Changes shown* switch hides it to show the true screen), and *no visible change* is badged.

**Desk or phone.** Started from a remote device (the harness says Remote Control, or Ben says he is away), the
artifact IS the walkthrough: he cannot reach the dev server. At a desk, also start a server on a seeded throwaway
database (appendix; a measured free port, signed in as Ben, no auto-reload) so he can drive any check himself, and
put its address in `server`. If it is unclear, ask once.

## 4. The walk

- **Each feedback item gets one line:** `Noted — slice: <slice name>` (§5), and the same note on its card: write
  `checks/c<n>` (`{n, state, slice, note}`; state `noted`, `ok`, `fixed`, `recheck` or `regression`) with the
  `ArtifactData` tool. Nothing else in chat. Don't argue, propose or summarise.
- **A direct question gets a full answer, grounded in the code.** Never from memory. Record it as a finding if the
  answer exposes a gap.
- **Speak up unasked only on a clearly large error**: a misreading of what the app does, or a request that breaks a
  standing rule (its CLAUDE.md, its ADRs). Two lines, then back to *Noted*.
- **Fix trivial bugs live** (a one-line defect, no product judgement) in a walkthrough worktree on `origin/master`:
  red test first, fix, re-record that check, republish, then "fixed: see #n". Anything bigger is only recorded.
- **Seed or record on request:** if Ben wants another state or another step, add the walk, record it, republish.

## 5. "Review complete": six slices, then the record

| Slice | What goes in it |
|---|---|
| **0 · Regressions** | Anything now WORSE than before (the before/after pairs are the first place to look), including a change that undid something Ben once asked for (`git log -S`, the bug history). Flagged against the next deploy. |
| **1 · Plain bugs** | Wrong by an existing rule; no design needed. The live fixes are listed here as *fixed*. |
| **2 · Functional changes** | Behaviour Ben described in his own words. Buildable as stated. |
| **3 · Needs a ruling** | Two or more real options. |
| **4 · Surface reviews** | "This page needs a review": one row per screen, his words as the review's seed. |
| **5 · Parked** | Mentioned but not wanted now. Goes to the ideas board. |

**Rule slice 3 straight away**: batches of up to four, recommendation first, options as what he would see
(`standards/examples-first.md`). A ruled item moves to slice 1, 2 or 5. Then write `meta/summary` (`{phase:
"complete", slices: [{name, items}], rulings, doc}`) so the artifact shows the outcome.

**Then record every finding on its screen** (standard §4, *Records*): one `kind = "walkthrough"` entry per screen,
dated, one `[[entry.finding]]` each with `severity`, `outcome` (`fixed` for a live fix, `open` + `doc` for one
sent to a slice, `parked`, or `ben`/`ruled` with its reason), `what`, and **`caught_by`: the layer that should
have caught it** (`scope` a scenario was missing · `canon` a shared component or rule was missing · `review` the
reviewer should have seen it · `lint` it is measurable · `test` a test should pin it · `taste` only Ben could say).
Add `row` (the friction-checklist line) or `component` where one applies: those are what the report counts as
repeats. A finding on no registered screen goes in the walkthrough doc only.

## 6. Persist and hand off

1. **The walkthrough doc** (appendix: its location), for a fresh session that never saw this chat: the checklist,
   the slices (findings, screens, what done looks like), the rulings, the live fixes and their tests, the owed
   desk checks, and the artifact's link.
2. **Run `review_report.py --app .`** and put its *leak* line and any *promote* rows in the doc. **A promote row
   becomes a slice-1 or slice-2 item** in the layer it names (a catalogue component, a checklist line, a lint rule,
   a ratchet). That is how the method improves.
3. **One ledger line** pointing at the doc with the app's not-yet-built marker, one index row, parked items to the
   ideas board (appendix).
4. **Live fixes and the records** land together: full suite, the app's record checks and the gate, then the
   appendix's landing path. No deploy.
5. **One new-session card per slice**, each brief naming the doc and its slice; slice 4 one per screen; slice 0
   marked for attention before the next deploy.
6. **Stop any server** you started (by its process id, after checking its command line). The worktrees go once
   the landing merges.

## Pairs with

- **`scope`**: its scenarios become flows (slice 0), so the build, the reviewer and Ben all walk Ben's examples.
- **`surface-review`**: the same engine during the build; slice 4's sessions run it.
- **`deploy`**: runs after; slice 0 is the one to read before pressing it.
