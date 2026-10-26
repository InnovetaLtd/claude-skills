# Wire one or more project repos to the Innoveta skills marketplace.
# Writes extraKnownMarketplaces + enabledPlugins into each repo's
# .claude/settings.json (merging with what's there). Does not commit.
#
# Usage: scripts\enable-in-repo.ps1 [repo-path ...]   (default: current directory)
param([string[]]$Repos = @((Get-Location).Path))
$ErrorActionPreference = 'Stop'

$marketplaceRepo = if ($env:INNOVETA_MARKETPLACE_REPO) { $env:INNOVETA_MARKETPLACE_REPO } else { 'InnovetaLtd/claude-skills' }
$pluginList = Join-Path (Split-Path $PSScriptRoot -Parent) 'default-plugins.txt'
$plugins = Get-Content $pluginList | Where-Object { $_ -notmatch '^\s*(#|$)' }

foreach ($repo in $Repos) {
    Write-Host "== $repo"
    $root = git -C $repo rev-parse --show-toplevel 2>$null
    if (-not $root) { Write-Host '   not a git repo, skipping'; continue }
    Push-Location $root
    try {
        claude plugin marketplace add $marketplaceRepo --scope project
        foreach ($plugin in $plugins) { claude plugin install $plugin.Trim() --scope project }
        Write-Host '   done: review and commit .claude/settings.json'
    } finally { Pop-Location }
}
