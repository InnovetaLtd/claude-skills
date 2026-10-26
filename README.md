# Innoveta Claude Skills

The single source of truth for the Claude Code skills Innoveta uses across every project, on every machine and in every cloud session. It is a Claude Code **plugin marketplace**: one repo, installed the same way everywhere.

| Plugin | What it is | Source |
|---|---|---|
| `innoveta-method` | Innoveta's project-records methodology: tiered docs, cold-start session handoffs, parallel-safe ideas capture/triage, config-driven gated deploys. See [its README](plugins/innoveta-method/README.md). | This repo, `plugins/innoveta-method/` |
| `impeccable` | Paul Bakaus's frontend design skill, agents and hooks (`/impeccable polish`, `audit`, `critique`…). | [`pbakaus/impeccable`](https://github.com/pbakaus/impeccable), pinned to a release tag |
| `mattpocock-skills` | Matt Pocock's engineering skills (grilling, TDD, code review, domain modelling, diagnosing bugs…). | [`mattpocock/skills`](https://github.com/mattpocock/skills), pinned to a commit |

## How skills reach a session

Every project repo carries a small `.claude/settings.json` that names this marketplace and the plugins to enable. Because the setting travels with the repo, it works identically wherever the repo is opened: a local clone, the desktop app, an IDE, or a Claude Code cloud session. Nothing has to be installed per machine.

The resulting settings look like this:

```json
{
  "extraKnownMarketplaces": {
    "innoveta": { "source": { "source": "github", "repo": "InnovetaLtd/claude-skills" } }
  },
  "enabledPlugins": {
    "innoveta-method@innoveta": true,
    "impeccable@innoveta": true,
    "mattpocock-skills@innoveta": true
  }
}
```

Locally, the first time a repo is opened Claude Code asks you to trust it and install the plugins. That is once per repo per machine.

## Wiring a project

Run from a clone of this repo, pointing at one or more project repos (defaults to the current directory):

```bash
scripts/enable-in-repo.sh ~/dev/egb-buildmanager ~/dev/egb-serviceapp
```

```powershell
scripts\enable-in-repo.ps1 C:\dev\egb-buildmanager, C:\dev\egb-serviceapp
```

The script uses the Claude Code CLI to merge the marketplace and plugins into each repo's `.claude/settings.json`, keeping any existing settings. It does not commit, so review the diff and commit it yourself.

The plugins it enables are listed once, in [`default-plugins.txt`](default-plugins.txt). A project that doesn't need one can set it to `false` in its own settings.

## Maintaining

- **Edit an Innoveta skill:** change it under `plugins/innoveta-method/`, then bump `version` in `plugins/innoveta-method/.claude-plugin/plugin.json` so installed copies pick up the change.
- **Upgrade a third-party plugin:** change its `ref` (impeccable) or `sha` (Matt Pocock) in [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json). Pinning means upstream changes never alter your skills until you choose to take them.
- **Add a plugin:** add an entry to `.claude-plugin/marketplace.json` and a line to `default-plugins.txt`, then re-run the script on your repos.
- **Validate before pushing:** `claude plugin validate .`

Install each plugin through this marketplace only. If the same skills are also enabled through the claude.ai plugin directory, every skill appears twice, so disable the claude.ai copy.
