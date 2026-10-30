---
name: surface-review
description: Goal-oriented review of a screen or flow in an Innoveta app, run against the RUNNING surface with seeded data shapes, by an independent fresh agent, recorded per screen so the app's landing gate can see it was done. Use when asked to "critique", "review the page/layout/UX", "is this intuitive", as the last step of any slice that changes a screen, or BEFORE designing a new screen (to write its goal). Not a code review and not a bug hunt.
---

# Surface review: does this screen do its JOB?

**The standard is ONE file: `standards/surface-review.md` in this plugin.** Read it in full first; this skill is
the procedure, and repeats none of the standard. The app's config is `surface-review.toml` at its root (no file:
run `/surface-review-init` first). Its appendix names its component catalogue and terminology docs.

## Designing, not reviewing?
Write the screen's four goal lines (standard §1) from the user's words in the brief, register the screen in the
app's registry with them, and stop: the design follows the questions in order.

## The procedure (as the builder)

1. **Map the change to screens.** A changed page template is its screen (the registry's `templates`). A changed
   shared file (the config's `shared` globs) needs the lint on every screen, and a review only of the screens the
   change was MEANT to alter. An unregistered screen you touched registers now: its goal lines, its setups in the
   app's seed command (at least `empty` and `typical`), and its record.
2. **Run the lint** on those screens (the app's wrapper, e.g. `python scripts/surface_method.py lint
   --changed-since origin/master`). Fix every new failure; a fix shrinks the baseline.
3. **Spawn the reviewer: a fresh agent, same model** (standard §4, Independence). Its brief is ONLY: the
   standard's path, the registry entry, the dev server's address for each setup (seed them first), the screen's
   rulings from its record, and "report in standard §3's shape, every finding rated major/moderate/minor with its
   evidence". ⚠️ Never your summary of what you changed, never the diff: a reviewer handed the builder's claims
   checks the claims, not the page.
4. **Deal with each finding.** Fix what is in scope; a minor finding may be waived with a reason; anything you
   cannot fix becomes Ben's call: take phone + desk screenshots, send them to him, and add one line to the
   app's owed ledger. The change still lands.
5. **Repeat full passes with a NEW reviewer** until a pass finds nothing above minor. Repeats, re-wordings and
   ruled points do not count; if a pass only re-words earlier findings, stop.
6. **Write the record** (`<records>/<slug>.md`): append an `[[entry]]` with `kind = "review"`, the date, the
   screen's fingerprint (`check_surface_reviews.py --fingerprint <slug>`), the number of passes, and one
   `[[entry.finding]]` per finding (`id`, `severity`, `outcome`, `what`, `reason` where waived or Ben's). Add any
   new ruling of Ben's under *Rulings*. A change that needed no review appends `kind = "na"` with its `reason`.
7. **Run the gate** (`python scripts/surface_method.py gate`) before handing the change to the landing path.

## Reporting to Ben
Lead with the ranking, not the method: the goal, what works, the findings that are his calls (with the
screenshots), and what you fixed in one line each. Put his calls through the question tool, recommended answer
first.
