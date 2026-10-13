[CmdletBinding()]
param(
    [ValidateSet('Plan', 'Switch', 'Rollback')]
    [string]$Action = 'Plan',
    [switch]$Execute
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$finalRoot = 'D:\FPGA\captain_integration'
$archiveRoot = 'D:\FPGA\AFDX_archive\workspaces_20261012'
$legacyBackup = Join-Path $archiveRoot 'captain_integration_pre_stageF_20261012'
$failedWorkspace = Join-Path $archiveRoot 'captain_integration_stageF_failed_20261012'
$workspaceManifest = Join-Path $archiveRoot 'workspace_manifest.json'
$transitionArchive = 'D:\FPGA\AFDX_archive\workspace_transition_20261013'
$candidateArchive = Join-Path $transitionArchive 'migration_candidate_20261012'
$e3CloneArchive = Join-Path $transitionArchive 'e3_ascii_clone_20261012'
$remote = 'https://github.com/zhixiangyuan/FPGA-.git'
$approvedMain = '9d5b85dd67bcf356bdc47c4aaf3336d2a863f832'
$approvedV10 = '668094d8d4bcb5e4f2a447274b61a88129c991ec'

function Assert-FpgaPath {
    param([string]$Path)
    $full = [IO.Path]::GetFullPath($Path)
    if (-not $full.StartsWith('D:\FPGA\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing a path outside D:\FPGA: '$full'."
    }
    return $full
}

$finalRoot = Assert-FpgaPath $finalRoot
$archiveRoot = Assert-FpgaPath $archiveRoot
$legacyBackup = Assert-FpgaPath $legacyBackup
$failedWorkspace = Assert-FpgaPath $failedWorkspace
$workspaceManifest = Assert-FpgaPath $workspaceManifest
$transitionArchive = Assert-FpgaPath $transitionArchive
$candidateArchive = Assert-FpgaPath $candidateArchive
$e3CloneArchive = Assert-FpgaPath $e3CloneArchive

function Get-GitOutput {
    param([string]$Repository, [string[]]$GitArgs)
    $output = & git -C $Repository @GitArgs 2>&1
    if ($LASTEXITCODE -ne 0) { throw "git -C '$Repository' $($GitArgs -join ' ') failed: $($output -join ' ')" }
    return (($output | Out-String).Trim())
}

function Assert-WorkspaceMatchesManifest {
    param([string]$Path, [string]$ExpectedRoot)
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { throw "Workspace is missing: '$Path'." }
    $manifest = Get-Content -LiteralPath $workspaceManifest -Raw | ConvertFrom-Json
    if ($manifest.result -cne 'PASS' -or $manifest.verified_files -ne 17261 -or $manifest.verified_bytes -ne 2573320124) {
        throw 'The archived workspace manifest is not the expected verified 17,261-file snapshot.'
    }
    if ([IO.Path]::GetFullPath($manifest.source).TrimEnd('\') -ine [IO.Path]::GetFullPath($ExpectedRoot).TrimEnd('\')) {
        throw "Workspace manifest source mismatch: '$($manifest.source)'."
    }
    if ([IO.Path]::GetFullPath($manifest.archive_copy).TrimEnd('\') -ine [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $workspaceManifest) 'captain_integration')).TrimEnd('\')) {
        throw "Workspace manifest archive-copy path mismatch: '$($manifest.archive_copy)'."
    }

    $base = [IO.Path]::GetFullPath($Path).TrimEnd('\') + '\'
    $actual = @(Get-ChildItem -LiteralPath $Path -File -Force -Recurse -ErrorAction Stop)
    if ($actual.Count -ne $manifest.verified_files) { throw "File count mismatch under '$Path': expected $($manifest.verified_files), got $($actual.Count)." }
    $expectedByPath = @{}
    foreach ($item in $manifest.files) { $expectedByPath[$item.path] = $item }
    foreach ($file in $actual) {
        $relative = $file.FullName.Substring($base.Length).Replace('\', '/')
        if (-not $expectedByPath.ContainsKey($relative)) { throw "Unexpected file under '$Path': '$relative'." }
        $expected = $expectedByPath[$relative]
        if ($file.Length -ne $expected.size_bytes) { throw "File size mismatch: '$relative'." }
        $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($hash -cne $expected.sha256.ToLowerInvariant()) { throw "SHA-256 mismatch: '$relative'." }
        $null = $expectedByPath.Remove($relative)
    }
    if ($expectedByPath.Count -ne 0) { throw "Missing $($expectedByPath.Count) files under '$Path'." }
    Write-Output "WorkspaceManifest=PASS; Root=$Path; Files=$($manifest.verified_files); Bytes=$($manifest.verified_bytes)"
}

function Assert-StageFSourceAndRemote {
    param([string]$Repository)
    if ((Get-GitOutput $Repository @('branch', '--show-current')) -cne 'dev') { throw 'Candidate source repository must be on dev.' }
    $status = & git -C $Repository status --porcelain=v1
    if ($LASTEXITCODE -ne 0 -or @($status).Count -ne 0) { throw 'Candidate source repository must be clean before cutover.' }
    $branchText = Get-GitOutput $Repository @('branch', '--format=%(refname:short)')
    $branches = @($branchText -split "`r?`n" | Where-Object { $_ })
    if (($branches -join ',') -cne 'dev,main') { throw "Expected only local main/dev branches; found '$($branches -join ',')'." }
    if ((Get-GitOutput $Repository @('remote', 'get-url', 'origin')) -cne $remote) { throw 'Candidate origin URL is incorrect.' }

    $fetch = & git -C $Repository fetch origin --tags 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Could not refresh GitHub refs: $($fetch -join ' ')" }
    $localMain = Get-GitOutput $Repository @('rev-parse', 'refs/heads/main')
    $localDev = Get-GitOutput $Repository @('rev-parse', 'refs/heads/dev')
    $remoteMain = Get-GitOutput $Repository @('rev-parse', 'refs/remotes/origin/main')
    $remoteDev = Get-GitOutput $Repository @('rev-parse', 'refs/remotes/origin/dev')
    if ($localMain -cne $approvedMain -or $remoteMain -cne $approvedMain) { throw "main no longer matches the approved E2 merge '$approvedMain'." }
    if ($localDev -cne $remoteDev) { throw 'Candidate dev is not synchronized with GitHub dev.' }
    & git -C $Repository merge-base --is-ancestor refs/heads/main refs/heads/dev
    if ($LASTEXITCODE -ne 0) { throw 'main is not an ancestor of dev.' }
    $tag = Get-GitOutput $Repository @('rev-parse', 'afdx-v1.0-stage1-system-verified-2026-10-12^{commit}')
    if ($tag -cne $approvedV10) { throw 'The original V1.0 stable tag moved.' }
    Write-Output "RemoteRefs=PASS; Main=$localMain; Dev=$localDev; V1Tag=$tag"
}

function Show-Plan {
    Write-Output "Action=$Action"
    Write-Output "LegacyRoot=$finalRoot"
    Write-Output "LegacyArchive=$legacyBackup"
    Write-Output "UnifiedRoot=$finalRoot"
    Write-Output "FailureArchive=$failedWorkspace"
    Write-Output "WorkspaceManifest=$workspaceManifest"
    Write-Output "AfterSuccessArchiveCandidate=$candidateArchive"
    Write-Output "AfterSuccessArchiveE3Clone=$e3CloneArchive"
    Write-Output "AuxiliaryArchiveManifest=$(Join-Path $transitionArchive 'archive_manifest.json')"
    Write-Output 'Preflight=GitHub refs, clean dev, two local branches, old-root/archive hashes, and at least 10 GiB free space'
    Write-Output 'PostClone=Unified verification plus full ModelSim RTL Golden verification'
    Write-Output "Remote=$remote"
    Write-Output 'No files or directories were moved.'
}

if (-not $Execute -or $Action -eq 'Plan') {
    Show-Plan
    if ($Action -ne 'Plan' -and -not $Execute) {
        Write-Output 'DryRun=TRUE; pass -Execute only after the separate Stage F approval.'
    }
    exit 0
}

if (-not (Test-Path -LiteralPath $archiveRoot -PathType Container)) {
    throw "Archive directory is missing: '$archiveRoot'."
}

if ($Action -eq 'Switch') {
    if (-not (Test-Path -LiteralPath $finalRoot -PathType Container)) {
        throw "The legacy root is missing: '$finalRoot'."
    }
    if (Test-Path -LiteralPath (Join-Path $finalRoot '.git')) {
        throw "The legacy root unexpectedly has a top-level .git directory: '$finalRoot'."
    }
    if (Test-Path -LiteralPath $legacyBackup) {
        throw "The pre-Stage-F archive destination already exists: '$legacyBackup'."
    }
    if (Test-Path -LiteralPath $failedWorkspace) {
        throw "The failure archive destination already exists: '$failedWorkspace'."
    }
    $candidateRoot = Split-Path -Parent $PSScriptRoot
    Assert-StageFSourceAndRemote $candidateRoot
    Assert-WorkspaceMatchesManifest $finalRoot 'D:\FPGA\captain_integration'
    Assert-WorkspaceMatchesManifest (Join-Path (Split-Path -Parent $workspaceManifest) 'captain_integration') 'D:\FPGA\captain_integration'
    if ((Get-PSDrive -Name D).Free -lt 10GB) { throw 'D: has less than 10 GiB free; stopping before any directory move.' }
    $blockingApps = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'eLinx*.exe' -or $_.Name -in @('vsim.exe', 'vsimk.exe') })
    if ($blockingApps.Count -ne 0) { throw "Close eLinx/ModelSim before the directory move: $((($blockingApps | Select-Object -ExpandProperty Name -Unique) -join ', '))." }
    $codeWindows = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'Code.exe' -and $_.CommandLine -match 'captain_integration|AFDX_E3_dev_clone_20261012' })
    if ($codeWindows.Count -ne 0) { throw 'VS Code command lines still reference the legacy/candidate/verification workspace. Close those workspace windows before moving.' }

    Move-Item -LiteralPath $finalRoot -Destination $legacyBackup
    try {
        & git clone $remote $finalRoot
        if ($LASTEXITCODE -ne 0) { throw "git clone failed with exit code $LASTEXITCODE." }
        & git -C $finalRoot fetch origin --tags
        if ($LASTEXITCODE -ne 0) { throw "git fetch failed with exit code $LASTEXITCODE." }
        & git -C $finalRoot switch --track -c dev origin/dev
        if ($LASTEXITCODE -ne 0) { throw "Creating local dev failed with exit code $LASTEXITCODE." }

        $verifyScript = Join-Path $finalRoot 'scripts\verify_unified_workspace.ps1'
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyScript
        if ($LASTEXITCODE -ne 0) { throw "Unified workspace checks failed with exit code $LASTEXITCODE." }

        $python = Get-Command python -ErrorAction Stop
        $rtlOutput = @(& $python.Source (Join-Path $finalRoot 'scripts\run_v1.py') 2>&1)
        if ($LASTEXITCODE -ne 0) { throw "ModelSim RTL regression failed with exit code $LASTEXITCODE. Output: $($rtlOutput -join ' ')" }
        $passLines = @($rtlOutput | ForEach-Object { "$_" } | Where-Object { $_ -match '^V1_RTL_RESULT PASS ' })
        if ($passLines.Count -ne 1) { throw 'ModelSim runner did not emit exactly one V1_RTL_RESULT PASS line.' }
        $runPath = $passLines[0].Substring('V1_RTL_RESULT PASS '.Length).Trim()
        & $python.Source (Join-Path $finalRoot 'scripts\verify_v1.py') $runPath
        if ($LASTEXITCODE -ne 0) { throw "Independent ModelSim Golden verification failed with exit code $LASTEXITCODE." }

        & git -C $finalRoot status --short --branch
        if ($LASTEXITCODE -ne 0) { throw 'Could not read the new workspace status.' }
        Write-Output "Switch=COMPLETE; the active branch is dev; ModelSimRTL=PASS; Run=$runPath"
    }
    catch {
        $validationError = $_.Exception.Message
        if (Test-Path -LiteralPath $finalRoot) {
            try {
                Move-Item -LiteralPath $finalRoot -Destination $failedWorkspace
            }
            catch {
                $rollbackError = $_.Exception.Message
                throw "Validation failed and the new workspace could not be moved aside. Original workspace remains intact at '$legacyBackup'. Validation error: $validationError; rollback error: $rollbackError"
            }
        }
        if ((Test-Path -LiteralPath $legacyBackup) -and -not (Test-Path -LiteralPath $finalRoot)) {
            Move-Item -LiteralPath $legacyBackup -Destination $finalRoot
        }
        throw $validationError
    }
    exit 0
}

if ($Action -eq 'Rollback') {
    if (-not (Test-Path -LiteralPath $legacyBackup -PathType Container)) {
        throw "The pre-Stage-F legacy archive is missing: '$legacyBackup'."
    }
    if (Test-Path -LiteralPath $failedWorkspace) {
        throw "The failure archive destination already exists: '$failedWorkspace'."
    }
    if (Test-Path -LiteralPath $finalRoot) {
        Move-Item -LiteralPath $finalRoot -Destination $failedWorkspace
    }
    Move-Item -LiteralPath $legacyBackup -Destination $finalRoot
    Write-Output 'Rollback=COMPLETE; the original workspace is restored.'
    exit 0
}
