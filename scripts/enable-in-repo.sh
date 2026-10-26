#!/usr/bin/env bash
# Wire one or more project repos to the Innoveta skills marketplace.
# Writes extraKnownMarketplaces + enabledPlugins into each repo's
# .claude/settings.json (merging with what's there). Does not commit.
#
# Usage: scripts/enable-in-repo.sh [repo-path ...]   (default: current directory)
set -euo pipefail

MARKETPLACE_REPO="${INNOVETA_MARKETPLACE_REPO:-InnovetaLtd/claude-skills}"
PLUGIN_LIST="$(cd "$(dirname "$0")/.." && pwd)/default-plugins.txt"

[ "$#" -eq 0 ] && set -- "$PWD"

for repo in "$@"; do
  echo "== $repo"
  (
    cd "$repo" 2>/dev/null || { echo "   not found, skipping"; exit 0; }
    git rev-parse --show-toplevel >/dev/null 2>&1 || { echo "   not a git repo, skipping"; exit 0; }
    cd "$(git rev-parse --show-toplevel)"
    claude plugin marketplace add "$MARKETPLACE_REPO" --scope project
    grep -vE '^\s*(#|$)' "$PLUGIN_LIST" | while read -r plugin; do
      claude plugin install "$plugin" --scope project
    done
    # Same plugin enabled from another marketplace would load twice: flag it.
    grep -vE '^\s*(#|$)' "$PLUGIN_LIST" | while read -r plugin; do
      grep -oE "\"${plugin%@*}@[^\"]+\"" .claude/settings.json | grep -v "\"$plugin\"" \
        | sed 's/^/   WARNING: duplicate, remove from .claude\/settings.json: /' || true
    done
    echo "   done: review and commit .claude/settings.json"
  )
done
