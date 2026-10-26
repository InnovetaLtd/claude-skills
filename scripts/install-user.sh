#!/usr/bin/env bash
# Install every plugin in default-plugins.txt at USER scope on this machine.
# For cloud environments, where a repo's .claude/settings.json does not
# trigger installs: run from the environment's setup script. Never fails the
# caller — a skills problem must not block a session from starting.
#
# Setup-script one-liner:
#   git clone -q --depth 1 https://github.com/InnovetaLtd/claude-skills /tmp/claude-skills && bash /tmp/claude-skills/scripts/install-user.sh
set -uo pipefail

MARKETPLACE_REPO="${INNOVETA_MARKETPLACE_REPO:-InnovetaLtd/claude-skills}"
PLUGIN_LIST="$(cd "$(dirname "$0")/.." && pwd)/default-plugins.txt"

command -v claude >/dev/null || { echo "claude-skills: claude CLI not found, skipping"; exit 0; }

claude plugin marketplace add "$MARKETPLACE_REPO" --scope user \
  || claude plugin marketplace update innoveta \
  || echo "claude-skills: marketplace add failed"
grep -vE '^\s*(#|$)' "$PLUGIN_LIST" | while read -r plugin; do
  claude plugin install "$plugin" --scope user || echo "claude-skills: install failed: $plugin"
done
exit 0
