[CmdletBinding()]
param(
    [string]$WorkspaceRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$RunRtl
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = [IO.Path]::GetFullPath((Get-Item -LiteralPath $WorkspaceRoot).FullName).TrimEnd([char[]]@('\'))

function Get-GitText {
    param([string[]]$GitArgs)
    $output = & git -C $root @GitArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "git $($GitArgs -join ' ') failed: $($output -join ' ')"
    }
    return (($output | Out-String).Trim())
}

$gitRoot = [IO.Path]::GetFullPath((Get-GitText @('rev-parse', '--show-toplevel'))).TrimEnd([char[]]@('\'))
if ($gitRoot -ine $root) {
    throw "Git root mismatch: expected '$root', got '$gitRoot'."
}

$branch = Get-GitText @('branch', '--show-current')
if ($branch -cne 'dev') {
    throw "Expected active development branch 'dev', got '$branch'."
}
$localBranchText = Get-GitText @('branch', '--format=%(refname:short)')
$localBranches = @($localBranchText -split "`r?`n" | Where-Object { $_ })
if (($localBranches -join ',') -cne 'dev,main') {
    throw "Expected exactly the long-lived local branches dev and main, got '$($localBranches -join ',')'."
}

$origin = Get-GitText @('remote', 'get-url', 'origin')
if ($origin -cne 'https://github.com/zhixiangyuan/FPGA-.git') {
    throw "Unexpected origin URL: '$origin'."
}

$main = Get-GitText @('rev-parse', 'refs/heads/main')
$originMain = Get-GitText @('rev-parse', 'refs/remotes/origin/main')
$dev = Get-GitText @('rev-parse', 'refs/heads/dev')
$originDev = Get-GitText @('rev-parse', 'refs/remotes/origin/dev')
if ($main -cne $originMain) { throw 'Local main is not synchronized with origin/main.' }
if ($dev -cne $originDev) { throw 'Local dev is not synchronized with origin/dev.' }
$mainUpstream = Get-GitText @('for-each-ref', '--format=%(upstream:short)', 'refs/heads/main')
$devUpstream = Get-GitText @('for-each-ref', '--format=%(upstream:short)', 'refs/heads/dev')
if ($mainUpstream -cne 'origin/main') { throw "main tracks '$mainUpstream', expected 'origin/main'." }
if ($devUpstream -cne 'origin/dev') { throw "dev tracks '$devUpstream', expected 'origin/dev'." }

$null = Get-GitText @('merge-base', '--is-ancestor', 'origin/main', 'origin/dev')
$stableTagCommit = Get-GitText @('rev-parse', 'afdx-v1.0-stage1-system-verified-2026-10-12^{commit}')
if ($stableTagCommit -cne '668094d8d4bcb5e4f2a447274b61a88129c991ec') {
    throw "The V1.0 stable tag moved: '$stableTagCommit'."
}

$frozenManifestPath = Join-Path $root 'FROZEN_CORE_MANIFEST.json'
$frozenManifest = @(Get-Content -LiteralPath $frozenManifestPath -Raw | ConvertFrom-Json)
if ($frozenManifest.Count -ne 13) { throw "Expected 13 frozen cores, got $($frozenManifest.Count)." }
foreach ($item in $frozenManifest) {
    $name = Split-Path -Leaf $item.snapshot
    $path = Join-Path (Join-Path $root 'vendor\frozen') $name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing frozen core: '$path'." }
    $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -cne $item.sha256.ToLowerInvariant()) { throw "Frozen core hash mismatch: '$path'." }
}

$goldenDir = Join-Path $root 'golden\V1.0_full_vo_315'
$goldenHashes = Get-Content -LiteralPath (Join-Path $goldenDir 'sha256.json') -Raw | ConvertFrom-Json
if ($goldenHashes.PSObject.Properties.Count -ne 8) {
    throw "Expected 8 Golden hash entries, got $($goldenHashes.PSObject.Properties.Count)."
}
foreach ($entry in $goldenHashes.PSObject.Properties) {
    $path = Join-Path $goldenDir $entry.Name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing Golden input: '$path'." }
    $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -cne $entry.Value.ToLowerInvariant()) { throw "Golden hash mismatch: '$path'." }
}

$edc = Join-Path $root 'elinx\AFDXV1\AFDXV1.srcs\constrs_1\new\clock_125mhz.edc'
if (-not (Test-Path -LiteralPath $edc -PathType Leaf)) { throw "Missing eLinx EDC: '$edc'." }
if ((Get-Content -LiteralPath $edc -Raw) -notmatch '-period\s+8\.000') {
    throw 'The eLinx EDC does not contain the expected 8 ns clock constraint.'
}

$python = Get-Command python -ErrorAction Stop
$modelsimBin = if ($env:MODELSIM_BIN) { $env:MODELSIM_BIN } else { 'D:\FPGA\Modlesim20.4\ModelSim20.4\win64' }
if (-not (Test-Path -LiteralPath (Join-Path $modelsimBin 'vsim.exe') -PathType Leaf)) {
    throw "ModelSim vsim.exe was not found under '$modelsimBin'. Set MODELSIM_BIN to the ModelSim bin directory."
}

$prepareOutput = & $python.Source (Join-Path $root 'scripts\prepare_v1_elinx.py')
if ($LASTEXITCODE -ne 0) { throw "eLinx project generator failed with exit code $LASTEXITCODE." }
$prepare = (($prepareOutput | Out-String) | ConvertFrom-Json)
if ($prepare.status -cne 'PREPARED_NOT_SYNTHESIZED' -or
    $prepare.top -cne 'AFDX_top' -or
    $prepare.device -cne 'EQ6HL45' -or
    $prepare.package -cne 'CSG225' -or
    $prepare.clock_constraint_ns -ne 8 -or
    $prepare.sources.Count -ne 16) {
    throw 'Generated eLinx project metadata does not match the approved configuration.'
}
if (@($prepare.sources | Where-Object { $_.sha256 -cne $_.snapshot_sha256 }).Count -ne 0) {
    throw 'Generated eLinx source hashes do not match canonical source hashes.'
}

$status = & git -C $root status --porcelain=v1
if ($LASTEXITCODE -ne 0) { throw 'Could not read Git worktree status.' }
if (@($status).Count -ne 0) { throw 'The Git worktree is not clean after workspace verification.' }

$rtlResult = 'NOT RUN'
if ($RunRtl) {
    & $python.Source (Join-Path $root 'scripts\run_v1.py')
    if ($LASTEXITCODE -ne 0) { throw "ModelSim RTL regression failed with exit code $LASTEXITCODE." }
    $rtlResult = 'PASS'
}

Write-Output 'UNIFIED_WORKSPACE_CHECK=PASS'
Write-Output "GitRoot=$gitRoot"
Write-Output "ActiveBranch=$branch"
Write-Output "Origin=$origin"
Write-Output "Main=$main"
Write-Output "Dev=$dev"
Write-Output "FrozenCores=$($frozenManifest.Count)"
Write-Output "GoldenHashes=$($goldenHashes.PSObject.Properties.Count)"
Write-Output "ELinxProject=$($prepare.project)"
Write-Output 'ELinxSynthesis=NOT RUN'
Write-Output "ModelSimRTL=$rtlResult"
Write-Output "ModelSimBin=$modelsimBin"
Write-Output 'GitStatus=CLEAN'
