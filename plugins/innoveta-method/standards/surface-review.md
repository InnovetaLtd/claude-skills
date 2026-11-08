# The surface review standard: design to it, review against it

**Ben, 2026-10-16:** *"this level of critique is the sort of thing I want as standard when we review things.
highly goal oriented … so that it becomes the default standard when critiquing but also becomes the goal when
initially designing features."* **Ben, 2026-10-29:** the machines do the nitpicks and the "did anyone check";
only the calls that are really his reach him.

This is the ONE definition, for every Innoveta app. Three things use it: a slice **brief** (§1: the goal is
written before any design), a slice's **worked-example pass** (its last step), and a **review** (the
`surface-review` skill). It does not replace an app's component catalogue (*how* a thing is built) or its test
suite (*whether* it works). This page asks whether the surface does the **job**, and §4 says how that is run,
recorded and enforced. Each app's own examples and catalogue pointers live in its appendix (the file its
`surface-review.toml` block names).

---

## §1 Start from the goal (design AND review)

Write these four lines before designing, and again before reviewing. If they cannot be written, stop and ask.
They live ONCE per screen, in the app's screen registry (§4).

1. **Who** uses it, and where: desk or phone, in the office or on site.
2. **The job**, in one sentence.
3. **The questions the job asks, in the order the user asks them.**
4. **Done looks like:** the state in which the user leaves satisfied.

The page's structure **follows the questions in order**. The first question is answered first, above the fold,
in words a newcomer understands.

## §2 The friction checklist

Walk the surface against each item, using real data shapes: empty / one / many, agreeing / disagreeing, desk and
375px, light and dark.

| # | Ask | The failure it catches |
|---|---|---|
| 1 | **Is the answer above the fold?** Chrome, flash messages and explainers sit below the answer, or go. | the verdict starts a third of the way down |
| 2 | **Does it say WHERE the problem is, not just THAT there is one?** Classify errors by *source* (whose problem) and by *severity*. | "differs by £359, fully explained" reads as done while 8 actions are open |
| 3 | **Exceptions first.** Problems sort to the top; clean rows collapse to one "✓ N matched" line. When there are no problems, the page is that one line. | the problems hide among the matches |
| 4 | **One place per fact.** A fact appears once; summaries count and link to it, they don't restate it. | the same item as a table row, a to-do and a summary row |
| 5 | **Act where you see it.** The fix sits on the row (an inline press reusing the existing component), not three pages away. | entering a value means leaving the page, once per row |
| 6 | **Batch like with like.** Several items needing the same action are one item listing the refs. | two to-dos for one request |
| 7 | **Don't ask for what the system knows.** Confirm, don't retype; one press when the facts are already read. | re-entering what a read already holds |
| 8 | **No hidden repeat cost.** A revisit, refresh or back must not re-run a paid read or lose typing. Every press lands back where you pressed it. | every visit costs another AI read; a press sends you to the top |
| 9 | **Columns earn their place.** A usually-redundant column goes behind a picker. Two columns that should agree become one *difference*. | Theirs + Ours + Match, where one *Difference* says it |
| 10 | **Colour carries meaning, not decoration,** and is never the ONLY signal. Shared tones and chips, tokens only. | an issue row that looks like a clean one |
| 11 | **Words: short labels, plain English, formal terms only where an auditor reads them.** A label that needs a sentence is the wrong label. | a column of sentences |
| 12 | **Is it built from the ONE origin?** The capability exists once; this surface is a carrier, not a copy. | a fourth hand-rolled send screen |
| 13 | **Is the arithmetic honest?** Totals reconcile exactly; a remainder is shown, never dropped. | an explanation £90 short of the difference |
| 14 | **What happens next time?** The next visit, the next record, the chain. | no link between this period and the last |
| 15 | **Is there another way to do this job?** One route per job: a second entry point to the same act is a finding. A fork is fine only where the work genuinely differs, asked as one question INSIDE the route; shortcuts (search, hub lists, links) lead to the route, never to a copy of it. | a paper uploaded to sit filed AND dropped at the point of recording: two routes, and the bugs live in the seam |

## §3 The output

1. **The goal**: §1's four lines, so the reader can disagree with the premise.
2. **What it does well**: briefly, so it isn't lost in the next change.
3. **Findings, ranked by cost to the job**, each **rated** (§4): what the user hits · which §2 row · the evidence
   (width, theme, data setup, what the page showed) · the concrete fix, naming the existing component it reuses.
4. **Recommendation**: what to build, and the **judgement calls that are Ben's**, as questions with a recommended
   answer first.

⚠️ **Read the real surface, not the template**: the review runs against the running page with seeded shapes.
⚠️ **Eyeball to discover, test to pin**: each fix that ships gets a test.

## §4 How it runs, is recorded and is enforced (rulings SR1–SR19, 2026-10-29)

**Per app** (written by `/surface-review-init`): `surface-review.toml` (the pinned method version, paths, and how
to prepare, seed and serve the app) · a **screen registry** (one entry per screen: templates, the four goal lines,
the `answer` element, data setups) · **one seed command** printing a setup's address (the reviewer, the lint and
the manuals all seed through it) · a **record per screen** (TOML block the gate reads, then prose and Ben's
rulings) · two **shrink-only lists**: page templates not yet registered, and the lint baseline.

**Flows (Ben, 2026-11-08: one review pipeline).** A screen's registry entry may carry `[[screen.flow]]`
entries: a scenario walked on the running screen (a `setup`, the `steps` a user takes, and what they should
`sees`, in the scope's words). A scope's slice 0 registers one per scenario. `surface_record.py` records them as
pictures through the same prepare, seed and serve as the lint; the builder walks its own pictures first, the
reviewer judges them, and the walkthrough shows them to Ben beside the same walk recorded on the live SHA.

**Records teach the method.** A record holds `review`, `na` and `walkthrough` entries; only the latest review or
n/a dates the screen. Every finding says where it was found (`origin`: lint, review, self-walk, walkthrough).
Every walkthrough finding also says which layer should have caught it (`caught_by`: scope, canon, review, lint,
test, taste). Where it applies, it names the friction-checklist `row` or the catalogue `component`.
`review_report.py` reads them all. It reports **the leak** (not-taste walkthrough findings per walkthrough: they
should fall) and **what repeats** (a row or component on two or more screens). A repeat is promoted into the
layer that should have caught it.

**Severity (SR9).** *Major*: the user gets the job wrong or cannot finish it (a misleading total, a dead end).
*Moderate*: extra presses, a trip off the page, a re-read. *Minor*: polish that does not change how the job goes.
The reviewer rates; Ben's ruling overrides.

**Outcomes (SR12).** Every finding ends **fixed**, **waived** (minor only, with a reason, SR12a), **ruled**
(SR12c) or **ben** (his call: the change lands as built, the call goes to the app's decision queue with phone +
desk screenshots, SR12b; an app with no queue yet uses its owed ledger).

**Ruled (SR12c, Ben 2026-11-04: *"happy for you to own plumbing and layout general decisions unless I have
explicitly requested a certain UI layout"*).** The builder decides a finding itself, at any severity, when it is
**layout** (arrangement, ordering, placement, folds, what sits above the fold) or **plumbing** (internal wiring a
user never reads). The record names the `decider`, the `scope` and a one-line `reason`. **Never ruled, always
ben:** money or rates · a stored value or code identifier · customer-facing words or e-mails · what a record
STATES to an auditor (its content and meaning; its arrangement is layout) · access or security · anything that
contradicts the screen's *Rulings*. An **explicit request** is any ruling recorded on the screen, an accepted
recommendation included: read the record's *Rulings* before ruling, and to undo one, ask. In doubt, it is ben.

**Independence (SR8).** The reviewer is a FRESH agent on the same model, briefed only with the registry entry,
the address and the setups, and the screen's rulings. Never the builder's summary or the diff.

**Stop rule (SR10).** Full passes until a pass finds nothing above minor. A finding that repeats an earlier one,
re-words it, or contradicts a ruling does not count. Minor findings are listed, not chased.

**The lint (SR14–SR17)**: at 375 px and desk, light and dark, it fails on sideways scroll · a wrapped button label
· a tap target under 44 px on the phone · a console error · contrast under 4.5:1 (3:1 large) · the `answer`
starting below the fold. It runs on the screens a change touches: a changed shared file selects the screens its
template graph, script tags or changed CSS selectors reach, and every screen whenever that cannot be pinned down
(an element or `:root` selector, a token app code builds, a file no page reaches); the release CI sweeps every
screen. A page that does not settle (network idle, fonts, two frames) fails the run. Today's failures sit in the baseline, which only shrinks.

**The gate (SR3–SR6, SR18)** refuses a change when: a page template is neither registered nor on the
unregistered list · an unregistered page changed (register it on touch) · a screen changed after its record's
latest entry (a fingerprint of its templates) · a finding has no outcome, or a waiver sits above minor · a
shrink-only list grew. An `n/a` entry with its reason passes and is printed, so it stays visible. Where it runs is
the app's landing path (a merge queue, or CI on push).
