# Examples first: how anything put to Ben is written

**Ben, 2026-10-30:** *"always provide real world examples of the feature, don't get bogged down in the syntax,
explain how the feature will work in practice with a tangible example. Allude to syntax where a necessary
decision needs to be made but lead with the execution of a real example."*

This is the ONE definition, for every Innoveta app and skill. It applies to anything a person reads to judge or
decide: scoping questions (`scope`), rulings and NEEDS-RULING options (bug intake), walkthrough checks, morning
reports, decision pages, PR descriptions written for Ben. It does not apply to code, tests or agent-to-agent
briefs.

## The four rules

1. **Lead with a worked example.** Before any explanation, show the thing happening: what arrives, who sees
   what first, what they press, what changes, what is stored, where it shows up later.
2. **Real nouns.** A named supplier, part number, quantity, price, build, site, date and the person's role, taken
   from the app's real records (dev seed, docs, live-like data). Never `Supplier A`, `foo`, `X`. Customer names:
   only those the repo's docs already name.
3. **Options are outcomes.** Each option says what the user would SEE and what would be true afterwards, in one
   line. Not how it is implemented.
4. **Syntax only where it decides something.** Name a field, model, table, migration or API only when it is the
   decision AND hard to reverse (a stored value, a schema change, a cross-app contract). One line, labelled
   *Under the hood*, after the example. Otherwise leave it out.

## The question format

```
❓ Q<n> — <short title>
**Example:** <the situation, with real nouns; say what changed from the last example>
**A —** <what happens / what they see>   **B —** <…>
➡️ Recommend <A>, because <the real-world reason>.
*Under the hood:* <only if it decides something irreversible>
```
Word it so "yes" accepts the recommendation.

## Before / after

Bad: *"Should `InvoiceLine` carry a nullable FK to `CostCentre`?"*

Good: *"A supplier's invoice arrives for 40 × M8×25 A4 bolts at £0.42 each, bought as workshop stock for no
build. Today the line can only go to a project or to stock. Should the person matching it be able to pick
'Workshop consumables' as the cost centre, line by line? → Recommend yes. Under the hood: a cost-centre column on
the invoice line, a migration; the stored value is the bit that's hard to undo."*

## Why

A decision asked in code makes Ben translate before he can judge, and hides the real-world consequence that IS
the judgement. In a scope, the agreed examples also become the acceptance scenarios a build must make true, so an
example written well is worth more than the prose around it.
