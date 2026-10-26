<!-- Place this at ideas/README.md in a project that uses the ideas workflow. -->

# Ideas — capture & triage convention

This directory is the **capture lane** of the parallel-safe ideas workflow. It exists so an "ideas / discussion" session can run *alongside* a live coding session without the two colliding on shared files.

## How it works (disjoint write lanes)

- **`/ideas` (discussion session)** writes to **exactly one** dated capture file in this directory and nothing else. It must NOT edit `CLAUDE.md`, `PROJECT_STATUS.md`, `ROADMAP.md`, `HISTORY.md`, `IDEAS_INBOX.md`, or app code.
- **`/ideas-triage` (coding session, when no discussion session is live)** reads the capture files and writes the **durable records** — `ROADMAP.md`, the `CLAUDE.md` queue + index, and the `IDEAS_INBOX.md` board — then deletes the processed capture files.

Two sessions, two non-overlapping write lanes ⇒ no edit conflicts.

## Capture file format

One file per discussion session: `ideas/YYYY-MM-DD-<topic>.md` (append `-2`, `-3`, … if today's topic already exists — never reuse another session's file). Each idea is a block:

```
## idea: <short title>
status: raw
relates-to: #NN   (omit if it maps to nothing existing)

<the idea, the reasoning behind it, and any decisions/trade-offs reached>
```

Capture the **reasoning and decisions**, not just the headline — triage needs the "why" to write a good roadmap item.

## Triage verdicts

Each idea block gets exactly one verdict: **Promote** (→ ROADMAP item/note, + build queue if scoped & agreed), **Park** (→ board's Parked section + a roadmap note), **Drop** (→ logged so it isn't re-litigated), or **Already done** (→ logged as shipped). Processed capture files are deleted; `git history` keeps the original.
