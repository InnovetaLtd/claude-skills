---
name: scope
description: Ben's feature-scoping session for an Innoveta app — turn a loose feature idea into a ruled, build-ready scope doc by walking REAL examples of the feature in use (this supplier's invoice for this part, this fitter on this build), grilling the open decisions as variants of those examples, and writing the agreed examples down as the acceptance scenarios a build must make true. Use when Ben says "scope", "let's scope X", "grill me on X", "how should X work", or brings a new feature or roadmap idea to design. NOT a bug pass (bug-intake), NOT a screen critique (surface-review), NOT a build — it writes one doc and stops.
---

# Scope: a feature, told as real examples, ruled, and ready to build

**Why this exists.** Ben's highest-value input is the scoping session. Two things waste it: questions asked in
code (`invoice.get_supplier()`), which he has to translate before he can judge them, and scope docs that agents
then build from without a test of whether they got it right. This skill fixes both with one move: **the examples
Ben agrees in the session ARE the acceptance tests.** Each one becomes a seeded data setup and a red test, so the
build cannot pass without making his examples true.

**Engine.** The interview mechanics are `grilling` (mattpocock-skills, pinned): the design tree, rounds, the
frontier, a recommended answer on every question, facts looked up rather than asked. Call the Skill tool with
`grilling` at Step 2 and follow it, **with the overrides below, which win where they differ.** Do not fork it;
upstream improvements keep arriving through the pin.

## The house rule: examples first

Read `standards/examples-first.md` in this plugin before the first question and follow it for every
question, option and playback. In short: lead with a real worked example, real nouns from the app's records,
options as what the user would SEE, and an *Under the hood* line only where an irreversible decision is being
made. Its question format replaces grilling's.

## Step 0 — Ground it before the first question (AFK)

Do this silently, then open with Step 1. Facts are your job (grilling's rule).
1. Read the app's scope appendix (`docs/scope-appendix.md`): where the roadmap, rulings, the terminology file,
   the component catalogue, the screen registry, the seed command, the scoping-doc location and the app's own
   coverage rows live. **No appendix ⇒ stop and offer to write one** (template: `templates/scope-appendix.md` in this plugin);
   a scope run blind to the app's rulings asks Ben what he has already decided.
2. Find what already exists, **searching for what it WOULD be called**, twice (model/service name AND
   route/template). A scope that re-designs built work is the most expensive failure there is.
3. **Read every earlier scope doc in the area to its END, not its header.** Status lines go stale; the rulings
   and "BUILT/LIVE" markers lower down are the truth (pilot, 2026-10-30: a doc headed "no app code until Ben
   rules" had been ruled and shipped two weeks earlier). Check the ledger and the code for what has shipped.
4. **Check every assumption the feature rests on is REAL** — the scheduler it reminds on, the reader it reads
   with, the screen it extends. Name what it rests on and grep for it (pilot: reminders were planned on a
   scheduler BM does not have).
5. Collect what is already ruled in this area: ADRs, decision registers, earlier scoping docs, `IDEAS_INBOX.md`,
   open owed lines. These answer questions so Ben is not asked them again.

## Step 1 — Tell today's story, then the anchor example

Open with two short stories in plain English, no code:
1. **Today:** *"Right now, when Inoxtube's invoice for those bolts comes in by mail, this is what happens: …"*,
   ending where it hurts. Ben corrects any misreading here, before anything is designed on top of it.
2. **The anchor:** the feature's happy path as one end-to-end example, with real nouns, from first touch to the
   last place the result shows up. Ask Ben to confirm or correct it. Everything later is a variant of this.

## Step 2 — Grill as variants of the anchor (grilling, with overrides)

Run `grilling`'s rounds. Overrides:
- **Every question is a variant of an example:** *"Same invoice, but goods-in only booked 38 of the 40"*. Name
  what changed from the anchor.
- **Options are what the user would SEE**, not implementations. Two or three, each a one-line outcome.
- **Format:** the question format in `standards/examples-first.md` (replaces grilling's).
  Word it so "yes" accepts the recommendation, as grilling says.
- **Seed the tree from the coverage list** (below). Anything an existing rule already decides is NOT asked: put
  it in a **"Decided by existing rule"** list in each round, with the rule cited, so Ben can veto it in one word.
- **Language** (`domain-modeling`'s discipline, the app's ONE terminology file — never a new GLOSSARY.md): challenge
  a term the moment it is fuzzy or two words are used for one thing, as a question in the standard format
  (*"lapsed" or "overdue"?*), and check the sibling apps for a clashing word. A ruled term is recorded per row:
  plain English (screen) · one-sentence definition · ISO / auditor word · code name (frozen) · words to avoid.

### The coverage list (frontier seeds — visit every branch; ask only what no rule decides)
| Branch | The example that probes it |
|---|---|
| **Every way in** | *The same invoice arrives by mail, by drag-and-drop, and typed in by hand. Does each one end the same way?* (one origin: a capability, not a screen) |
| **Data shapes** | empty / one / many · batch / serial · allocated / free · retired / live · agreeing / disagreeing |
| **Who** | who may do it (the app's permission flags), at the desk or on a phone, in the office or on site |
| **What an auditor sees** | where the result lands in the technical file / issued document, and its wording |
| **The same thing twice** | *The same certificate arrives by mail and as a phone photo.* Same file, same document, same day: what is caught, and where does the second copy point? |
| **Wrong and corrected** | *Sarah picked the wrong cost centre and spotted it on Friday.* Corrected how; what does the history show? (never a delete path) |
| **Money** | cost vs balance; VAT shown, never filed; ex-VAT cost |
| **The other app** | which app owns the fact (placement test); what the other app sees, and when |
| **Turning it on** | what makes it live and who presses it (the activator); what existing records it applies to |
| **Out of scope** | what Ben is NOT asking for, said out loud |
| **Another product** | *HomeOS has the same idea.* Share only if the two exchange data; otherwise name it as a reference implementation and copy its cases |
| **The app's own rows** | the appendix adds the branches only this app has (engine traps, document routing, …) |

## Step 3 — Play back the scenario book, get the yes

When the frontier is empty, play back **every agreed example as a numbered scenario** (S1, S2, …), each three to
six lines: *the setup* (real records), *what the user does*, *what they see and what is stored*. Then the decided-by-rule list
and the open items. Do not write anything until Ben says it's right (grilling's rule).

## Step 4 — Write the scope doc

One file at the app's scoping location (e.g. `docs/<feature>-scoping-<date>.md`), for a fresh build session
that never saw the chat. Sections, in this order:
1. **The idea in Ben's words** (quoted) and the destination in one line.
2. **Today** (the Step 1 story) and **the anchor example**.
3. **⭐ The scenario book.** S1…Sn as played back, each in plain English AND in this block, which the build's S0
   slice reads (Ben's ruling, 2026-10-30: the scope writes scenarios, never code):

   ```
   ### S3 — Forklift LOLER exam overdue
   - **Screens:** asset-list, asset-detail      (each becomes a seed setup `S3-forklift-overdue` on that screen)
   - **Setup:** the yard forklift (FL-01), LOLER thorough examination every 6 months, last done 1 May 2026;
     today is 2 Nov 2026.
   - **Does:** stores open the asset catalogue.
   - **Sees / stored:** FL-01 at the top, red, "LOLER exam 1 day overdue"; nothing is changed by looking.
   - **Slice:** 2
   ```
   Real nouns throughout (`standards/examples-first.md`). *This section is the deliverable: a build is done when
   every scenario is true on a fresh seed.*
4. **Screens.** For each screen touched or new: the four-line goal (who · the job · the questions in order · done
   looks like) — the screen registry's format, so the build registers it verbatim — and the named shared
   components it uses.
5. **Rulings.** Ben's answers (question → ruling, one line each) and the decided-by-rule list with citations.
6. **Under the hood.** Only the irreversible decisions: stored values, migrations, cross-app contract changes,
   with any engine-trap checks the appendix names. No file paths beyond what a decision needs.
7. **Language.** Every term the feature introduces or rules, in the terminology file's row format; written into
   that file in the same change as the doc.
8. **Slices.** Vertical, each demoable alone (`to-tickets`' rules): the scenarios it makes true, what blocks it,
   the files it may touch, its activator. **Slice 0 is always "scenarios"**, and blocks every other slice:
   - it registers each scenario as a seed setup on every screen it lists (`<screen>` + `S<n>-<slug>`, the app's
     ONE seed command), so surface review, the layout lint and the walkthrough walk Ben's examples;
   - it writes one test per scenario at the cheapest seam that proves it, against the interfaces the build
     actually chose, each marked **expected to fail** and naming its scenario (`S3`) and scope doc;
   - the marker is the ratchet: when a later slice makes a scenario true, the suite goes red until the marker
     is removed, so nothing goes quietly green and the scope doc's progress is the count of markers left;
   - it ends with a short list for Ben — *"this is what we will prove"*, one line per scenario — before the
     feature slices start.
9. **Out of scope / parked / cross-repo** — cross-repo items carry `none - <reason>` markers and say what proves them; parked items also go to `IDEAS_INBOX.md`.

Add the record markers the app uses for not-yet-built work (e.g. `PENDING-UNTIL`), and one pointer line in the
app's ledger/index.

## Step 5 — Stop

Report: the doc's path, the scenario count, the slice count, and any open question deliberately left for a
later round. **Do not build.** Building is a separate session (or lanes) reading this doc.

## Hard gates
- No question asked in code. No option without a real example.
- No "not built" claim off one search.
- No question Ben already ruled (cite the ruling instead).
- Nothing written before the playback is confirmed.
- A scenario that cannot be seeded and tested is not finished: sharpen it or mark it as a judgement check for the walkthrough.
- No code, seed or test written by this skill: Slice 0 of the build does that.
