---
name: surface-review-init
description: Set an Innoveta app up for the surface review - its surface-review.toml, screen registry, seed command, record folder, the shrink-only unregistered list and lint baseline, and the gate + lint wired into its landing path. Use once per app with screens, when there is no surface-review.toml yet, or when asked to "set up surface review" or "add the review gate" to an app.
---

# Surface review: set an app up

The method is `standards/surface-review.md` (§4 is what this sets up). The scripts stay in this plugin and are
**fetched at a pinned commit, never copied** into the app (Ben, 2026-10-30): the app pins `plugin_ref`.

1. **Write `surface-review.toml`** at the repo root from `templates/surface-review.toml`. Fill: `plugin_ref` (the
   current innoveta-method master commit), the registry / records / lists paths, `page_templates` + `page_marker`
   (what makes a template a PAGE rather than an include in this framework), `shared` globs, and `[lint]`: how to
   prepare a fresh scratch database, seed a setup, serve the app on `{port}`, the env that signs a dev user in,
   the theme switch, and the button / tap selectors of its component catalogue. Read the app's own dev docs for
   these: never guess a command into a gate.
2. **Write the registry** (`templates/screens.toml`) and register the screens the current work touches, with
   their goal lines from the user's words.
3. **Build the seed command**: one command, `<screen> <setup>` → prints `{"url": "/path"}`, idempotent, on top of
   the app's baseline seed. Add a test that the registry's setups and the command's agree.
4. **Bootstrap the lists**: `check_surface_reviews.py --app . --init-unregistered`, then
   `surface_lint.py --app . --all --write-baseline`. Both only shrink from here on.
5. **Wire the landing path**: a small wrapper in the app that keeps a cache clone of this repo, checks out
   nothing, and runs the scripts from `git show <plugin_ref>:<path>` (Build Manager's `scripts/surface_method.py`
   is the reference). Run the gate where a change lands (a merge queue: before the suite, the lint after it; CI on
   push: as steps) and the lint `--all` in the release CI.
6. **Add the app's appendix** (its catalogue, terminology and any worked examples) and a `## Surface review`
   pointer in its CLAUDE.md. Record the setup in its records and owed ledger as the app's rules require.
7. **Prove it**: a worked example where the gate refuses an unregistered page and a changed, unreviewed screen.
