[CmdletBinding()]
param(
    [switch]$SkipCpanel
)

$ErrorActionPreference = 'Stop'
$projectRoot = (git rev-parse --show-toplevel).Trim()
Set-Location -LiteralPath $projectRoot

$branch = (git branch --show-current).Trim()
if ($branch -ne 'production') {
    throw "Production releases must run from the production branch; current branch is '$branch'."
}

$changes = git status --porcelain
if ($changes) {
    throw 'The production working tree is not clean. Review and commit all release changes first.'
}

git push --set-upstream origin production
if ($LASTEXITCODE -ne 0) {
    throw 'The GitHub production push failed.'
}

if (-not $SkipCpanel) {
    $remotes = @(git remote)
    if ($remotes -contains 'cpanel') {
        git push cpanel production
        if ($LASTEXITCODE -ne 0) {
            throw 'The cPanel production push failed.'
        }
    }
    else {
        Write-Warning "GitHub was updated, but no 'cpanel' remote exists. Use cPanel Update from Remote and Deploy HEAD Commit, or add the cPanel SSH remote from the deployment runbook."
    }
}

Write-Host 'Production branch published successfully.'
