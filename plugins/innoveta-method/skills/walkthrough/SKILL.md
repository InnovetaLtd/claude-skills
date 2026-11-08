---
name: walkthrough
description: Ben's live review of what was just built in an Innoveta app. Claude prepares a dev server on a throwaway database, seeds an example record and any upload documents for each change, and publishes a numbered checklist artifact; started from a phone over Remote Control, it runs in watch mode, where Claude walks each check itself and the checklist shows step pictures. Ben gives numbered feedback one item at a time ("Noted — slice: …") and Claude fixes trivial bugs live. At "review complete" everything is grouped into six slices, the open calls are ruled there and then, and a walkthrough doc is written that a fresh session can pick up cold. Use when Ben says "walkthrough", "let me review what's built", "load up the dev server and give me a list of items to check", or after an integration lands and before /deploy. NOT a critique of one screen (surface-review), NOT a bug-report pass, NOT a deploy gate.
---

# Walkthrough: Ben walks what was built; Claude prepares, listens, then slices

**Why this exists.** A green suite is not evidence a surface is right; the walkthrough is the human half of that
rule. It spends Ben's review time on judging surfaces, not on hunting for data, typing test documents, or
remembering what he said. Designed with Ben in Build Manager on 2026-10-23, after the first session run this way.

**App specifics live in the app's walkthrough appendix** (`docs/walkthrough-appendix.md`; template:
`templates/walkthrough-appendix.md` in this plugin). It covers where the live SHA is recorded, how to build a
throwaway database, the server command and sign-in, the seed command, the upload folder, the record locations, and
the landing path. **No appendix ⇒ stop and offer to write one** from the app's dev docs; a walkthrough run blind
guesses commands into somebody's real database.

## 0. Desk or watch: decide before preparing

- **Watch mode when Ben started this from a remote device**: the harness says he is on Remote Control, or he says
  he is on his phone or away from the desk. His phone cannot reach the walkthrough server, so **Claude walks every
  check itself** and the checklist shows step pictures (§2b). If it is unclear, ask once.
- **Desk mode otherwise**: Ben walks the checks himself on the walkthrough server.
- **Both modes publish the checklist as an artifact** (§3): the checklist in one window, the app in another (desk
  mode), and Claude in a third for feedback. Nobody scrolls the chat to find item 7.

## 1. Scope: what gets a check

**Default: everything merged to master since the last deploy.** Find the live SHA (appendix) and read:
- the *Fixed* tables of every bug-intake and rulings doc written since then (appendix: where they live);
- `git log <live>..origin/master --merges` for the PR titles, and each PR's body for its activator;
- any scope doc whose slices landed in that range: **its scenarios are already seed setups**, walk those.

**Argument:** a PR number, a doc, or a branch narrows it to that.

**One check per user-visible change.** Merge several only when they sit on the same page and the same record.
Tooling, docs and test-only changes get no check.

## 2. Prepare (all before Ben sees anything)

1. **A walkthrough worktree** on `origin/master`, on a `walkthrough-<date>` branch. Every live fix (§3) lands here.
2. **A throwaway database** built by the appendix's command into the scratchpad. **Ben's everyday dev database is
   never seeded or migrated by this skill**, so nothing needs cleaning up afterwards.
3. **The server** started from the worktree on a **measured** free port (sibling sessions hold ports; check before
   you bind), signed in as Ben by the appendix's dev-user setting, with no auto-reload, and run as a background
   process. Restart it after any template or code edit.
4. **Seed one example per check through the real services.** Prefer the app's ONE seed command (the setup a scope
   or surface review already registered). Where none exists, add a setup to that command rather than writing a
   private script, copying the arrangement from the fix's own regression test. Make it idempotent and prefix every
   row so it is obviously a check record. Choose the **data shapes** that make the change visible: batch as well as
   serial, retired as well as live, two of something where the fix is about "more than one".
5. **Prerequisite state first** (goods booked in, totals saved, a deposit confirmed). Each check must start at the
   step Ben is meant to judge.
6. **Upload documents:** any step that needs a file gets a realistic one generated into the appendix's upload
   folder, named after its record (e.g. `CHK-B2 balance invoice PO-00029.pdf`). **Ben never drafts a test
   document** (his words, 2026-10-23).
7. **Pre-sweep at 375 px and in dark mode.** For every checklist URL, check that the page never scrolls sideways at
   the mobile size and that it renders in the dark theme. Any failure is **finding #0**, reported with the
   checklist. Ben then eyeballs desktop. Only phone-first surfaces carry a "check on a phone" step.
8. **Things that cannot work locally** (a cloud API fetch, a real AI read, a call to a sibling app) are named in the
   check's *What you should see*, so a local failure is never mistaken for a bug.

## 2b. Watch mode: record every check

1. **Write a plan per check**: the steps a user would take, ending at what Ben is judging, with a picture
   (`shot`) at every step whose screen he needs to see, captioned in plain English with what it shows. Use the
   phone viewport for phone-first screens and the desktop one otherwise. The plan format is in
   `scripts/walkthrough_watch.py`'s docstring.
2. **Record it**: `walkthrough_watch.py record plan.json --out <scratchpad>/shots`, with the Python the appendix
   names (it needs Playwright). **A check that stopped is a finding:** its last picture shows where and why. Fix
   the plan if the plan was wrong; otherwise it goes on the checklist as it is, under finding #0.
3. **Mark what pictures cannot judge**: a check whose point is *feel* (typing into a fiddly field, a drag, a tap
   target, the camera) gets `desk_only`. Its card says *walk at a desk later*, and the walkthrough doc lists it as
   an owed desk check, so it is never quietly passed.
4. **Re-recording**: after a live fix, record that one check again and republish (§3), then say "fixed: see #n".

## 3. The checklist artifact and the walk

**Build the checklist as an artifact page**, from `templates/walkthrough-checklist.html`, by
`walkthrough_watch.py page walk.json --out <scratchpad>/walkthrough-<date>.html` (`walk.json`: title, date, range,
mode, server, finding #0, and per check its number, title, ids, the data shapes that matter, where, and what you
should see; watch mode adds `--manifest`). Then:
1. **Publish** it with `capabilities: {db: {}, assets: {}}` (the `artifact-capabilities` skill holds the call shapes).
2. **Watch mode: upload the pictures** to the artifact's assets (`asset: true`, up to 25 files per call), write
   `{file: url}` to `urls.json`, rebuild with `--assets urls.json`, and republish the same file.
3. **Send Ben the link** with a one-line note on how to use it. Desk mode's links point at the walkthrough
   server; watch mode's pictures open full size when tapped.
4. **Notes go to the artifact's database, not into the page**: as each feedback item lands, write `checks/c<n>`
   (`{n, state, slice, note}`; state is `noted`, `ok`, `fixed`, `recheck` or `regression`) with the `ArtifactData`
   tool. The card updates while Ben watches. At "review complete", write `meta/summary` (`{phase: "complete",
   slices: [{name, items}], rulings, doc}`).

Order the checks with bug fixes on seeded records first, then checks on existing pages. Save the same table into
the walkthrough doc (§5); the artifact is Ben's view, **the doc stays the record** a fresh session reads.

**During the walk:**
- **Each feedback item gets one line:** `Noted — slice: <slice name>` (§4), and the same note on its card (§3.4).
  Nothing else. Don't argue, propose or summarise.
- **A direct question gets a full answer, grounded in the code.** Read it; never answer from memory. Record the
  question as a finding if the answer exposes a gap.
- **Speak up unasked only on a clearly large error.** That means a factual misreading of what the app does (thinking
  a built thing is missing, or the reverse), or a request that would break a standing rule of the app (its
  CLAUDE.md, its ADRs). Say it in two lines, then go back to *Noted*.
- **Fix trivial bugs live:** an obvious one-line defect with no product judgement (a missing dropdown option, a
  wrong label). Write the red test first in the walkthrough worktree, fix, restart the server, then tell Ben
  "fixed: re-check #n". Anything bigger is only recorded.
- **Seed on request:** if Ben needs a record or a document mid-walk, make it (§2.4–2.6) and say where it is.

## 4. "Review complete": six slices

Group every finding (numbered by checklist item) into:

| Slice | What goes in it |
|---|---|
| **0 · Regressions** | Anything now WORSE than before the change, including a change that undid something Ben once asked for (check `git log -S` and the bug history). Flagged against the next deploy. |
| **1 · Plain bugs** | Behaviour wrong by an existing rule; no design needed. The live fixes are listed here as *fixed*. |
| **2 · Functional changes** | Behaviour Ben described in his own words (e.g. "the X-ray sheet reads the HV sheet itself"). Buildable as stated. |
| **3 · Needs a ruling** | Two or more real options. |
| **4 · Surface reviews** | "This page needs a review": one row per screen, with what he said about it as the review's seed. Run by `surface-review`. |
| **5 · Parked** | Mentioned but not wanted now. Goes to the ideas board. |

**Then rule slice 3 straight away.** Ask in batches of up to four, recommendation first, options in plain English
with what he would see, written to `standards/examples-first.md`. A ruled item moves to slice 1 or 2 (or 5).
Don't write the doc until the rulings are in.

## 5. Persist and hand off

1. **The walkthrough doc** (appendix: its location), written for a fresh session that never saw this chat. It
   holds the checklist table; the slices, each with its findings, the screens it touches and what done looks
   like; the rulings taken; and the walkthrough branch's live fixes with their tests.
2. **One ledger line** pointing at the doc, with the app's not-yet-built marker, plus one index row (appendix).
3. **Parked items** go to the ideas board.
4. **Live fixes:** run the full suite on the walkthrough branch and the app's record checks, then land it by the
   appendix's landing path. No deploy.
5. **One new-session card per slice**, each brief naming the doc and its slice. Slice 4 gets one card per screen.
   Slice 0 is marked as wanting attention before the next deploy.
6. **Stop the server** (by its process id, after checking its command line) and close its browser tab. The worktree
   and its throwaway database go once the landing merges.

## Pairs with

- **`scope`**: a scope's scenarios are seed setups, so a walkthrough after a scoped build walks Ben's own examples.
- **`surface-review`**: slice 4's sessions run it.
- **`deploy`**: runs after; slice 0 is the one to read before pressing it.
