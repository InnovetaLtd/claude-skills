---
name: ideas
description: Run a parallel "ideas / discussion" session that captures and logs ideas WITHOUT editing the shared project records (CLAUDE.md, status/roadmap/history docs) or app code — so it can run safely alongside a live coding session. Use when the user says "ideas session", "discussion session", "let's brainstorm", "park this idea", "log this idea", or starts a second session just to talk through ideas.
---

# Ideas / discussion session (parallel-safe)

This session's job is to **think and capture, not to build or to edit the shared records**. It is designed to run **at the same time** as a separate coding session. The coding session edits `CLAUDE.md` / app code / the status/roadmap/history docs; this one must stay out of those files entirely, so the two never collide.

## The one hard rule — your write lane
- You may write to **exactly one file**: a dated capture file in the project's ideas directory (see "Find the ideas convention" below — usually `ideas/`).
- You must **NOT** edit `CLAUDE.md`, the status/roadmap/history docs, the ideas *inbox/board* file, or any application code/tests. Reading them for context is fine.
- If an idea clearly belongs in the roadmap/queue right now, **do not put it there yourself** — capture it in your one file and note "promote at triage". Triage happens later, in the coding session, when no discussion session is live.

This disjoint-writer rule is the whole point: discussion sessions write only their own capture file; triage writes only the inbox + roadmap, in the coding session. Two sessions, two non-overlapping write lanes ⇒ zero file-edit conflicts. The collision this removes is two sessions editing `CLAUDE.md` at once.

## Start of session
1. **Find the ideas convention.** Check `CLAUDE.md` for a section describing an ideas/discussion flow (often inside the `## Project records` block), and look for an `ideas/README.md` and an ideas inbox/board file (e.g. `IDEAS_INBOX.md`). If they exist, follow that project's format and directory exactly.
   - If the project has **no** ideas convention yet, create an `ideas/` directory and use the simple capture format below. Mention to the user that this is the first ideas session and you've started an `ideas/` folder.
2. **Pick this session's capture file:** `ideas/YYYY-MM-DD-<topic>.md` (today's date + a short topic slug). If one already exists for today's topic, append `-2`, `-3`, … — **never reuse another session's file**. Open it with a `# Discussion session — <date>` heading.
3. Skim the status/roadmap docs as needed for context, but treat them **read-only**.

## During the session
- Discuss freely. Stress-test ideas and push back on weak points (the user wants challenge, not a yes-man) — but the **output of every idea worth keeping is an entry appended to your one capture file**.
- Use the project's idea-block format if it has one; otherwise use:
  ```
  ## idea: <short title>
  status: raw
  relates-to: #NN   (omit if it maps to nothing existing)

  <the idea, the reasoning behind it, and any decisions/trade-offs reached>
  ```
- Capture the **reasoning and decisions**, not just the headline — triage needs the "why" to write a good roadmap item.

## End of session
- Make sure every idea worth keeping is written to the capture file.
- Tell the user the file path and that the ideas are ready for **triage** (done later in the coding session). Do **not** triage here, and do **not** touch the shared records.
