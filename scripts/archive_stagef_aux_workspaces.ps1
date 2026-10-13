[CmdletBinding()]
param([switch]$Execute)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$archiveRoot = 'D:\FPGA\AFDX_archive\workspace_transition_20261013'
$finalRoot = 'D:\FPGA\captain_integration'
$sources = @(
    [pscustomobject]@{
        Path = 'D:\FPGA\captain_integration_migration_candidate_20261012'
        Destination = Join-Path $archiveRoot 'migration_candidate_20261012'
    },
    [pscustomobject]@{
        Path = 'D:\FPGA\AFDX_E3_dev_clone_20261012'
        Destination = Join-Path $archiveRoot 'e3_ascii_clone_20261012'
    }
)

function Assert-FpgaPath {
    param([string]$Path)
    $full = [IO.Path]::GetFullPath($Path)
    if (-not $full.StartsWith('D:\FPGA\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing a path outside D:\FPGA: '$full'."
    }
    return $full
}

function Get-Snapshot {
    param([string]$Path)
    $base = [IO.Path]::GetFullPath($Path).TrimEnd('\') + '\'
    $files = @(Get-ChildItem -LiteralPath $Path -File -Force -Recurse -ErrorAction Stop)
    $rows = foreach ($file in $files) {
        [pscustomobject]@{
            path = $file.FullName.Substring($base.Length).Replace('\', '/')
            size_bytes = [long]$file.Length
            sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
    return @($rows)
}

foreach ($entry in $sources) {
    $entry.Path = Assert-FpgaPath $entry.Path
    $entry.Destination = Assert-FpgaPath $entry.Destination
    if (-not (Test-Path -LiteralPath $entry.Path -PathType Container)) { throw "Source workspace is missing: '$($entry.Path)'." }
    if (-not (Test-Path -LiteralPath (Join-Path $entry.Path '.git'))) { throw "Expected Git history is missing: '$($entry.Path)'." }
    if (Test-Path -LiteralPath $entry.Destination) { throw "Archive destination already exists: '$($entry.Destination)'." }
}

if (-not $Execute) {
    Write-Output "FinalRoot=$finalRoot"
    Write-Output "ArchiveRoot=$archiveRoot"
    foreach ($entry in $sources) { Write-Output "MoveAfterStageFPass=$($entry.Path) -> $($entry.Destination)" }
    Write-Output 'No files or directories were moved. Pass -Execute only after final-root validation and approval.'
    exit 0
}

if (-not (Test-Path -LiteralPath (Join-Path $finalRoot '.git'))) { throw 'The final unified Git root is not present.' }
if ((& git -C $finalRoot branch --show-current) -cne 'dev') { throw 'The final unified workspace must be active on dev.' }
$gitStatus = & git -C $finalRoot status --porcelain=v1
if ($LASTEXITCODE -ne 0 -or @($gitStatus).Count -ne 0) { throw 'The final unified workspace must be clean before archiving auxiliary workspaces.' }
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $finalRoot 'scripts\verify_unified_workspace.ps1')
if ($LASTEXITCODE -ne 0) { throw 'The final unified workspace verification failed.' }

$activeElnx = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'eLinx*.exe' })
if ($activeElnx.Count -ne 0) { throw 'Close eLinx before archiving the clone directories so no project is left pointing at a moved path.' }
$activeSim = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('vsim.exe', 'vsimk.exe') })
if ($activeSim.Count -ne 0) { throw 'Wait for ModelSim to exit before archiving clone directories.' }

New-Item -ItemType Directory -Path $archiveRoot -Force | Out-Null
$entries = @()
foreach ($source in $sources) {
    $rows = Get-Snapshot $source.Path
    $bytes = [long](($rows | Measure-Object -Property size_bytes -Sum).Sum)
    $entries += [pscustomobject]@{
        source = $source.Path
        archived_path = $source.Destination
        file_count = $rows.Count
        bytes = $bytes
        files = $rows
    }
}

$manifestPath = Join-Path $archiveRoot 'archive_manifest.json'
$manifest = [pscustomobject]@{
    result = 'MOVING'
    created_utc = [DateTime]::UtcNow.ToString('o')
    final_workspace = $finalRoot
    entries = $entries
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

try {
    foreach ($entry in $entries) {
        Move-Item -LiteralPath $entry.source -Destination $entry.archived_path
        $actualRows = Get-Snapshot $entry.archived_path
        if ($actualRows.Count -ne $entry.file_count) { throw "Post-move file count mismatch: '$($entry.archived_path)'." }
        $expectedByPath = @{}
        foreach ($row in $entry.files) { $expectedByPath[$row.path] = $row }
        foreach ($row in $actualRows) {
            if (-not $expectedByPath.ContainsKey($row.path)) { throw "Post-move unexpected file: '$($row.path)'." }
            $expected = $expectedByPath[$row.path]
            if ($row.size_bytes -ne $expected.size_bytes -or $row.sha256 -cne $expected.sha256) {
                throw "Post-move hash mismatch: '$($entry.archived_path)\$($row.path)'."
            }
            $null = $expectedByPath.Remove($row.path)
        }
        if ($expectedByPath.Count -ne 0) { throw "Post-move missing files: '$($entry.archived_path)'." }
        $entry | Add-Member -NotePropertyName status -NotePropertyValue 'PASS' -Force
        $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
    }
}
catch {
    $manifest.result = 'PARTIAL'
    $manifest | Add-Member -NotePropertyName error -NotePropertyValue $_.Exception.Message -Force
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
    throw "Auxiliary archive move/verification stopped. No files were deleted; moved directories remain at their archive paths and unmoved sources remain at their original paths. Manifest: '$manifestPath'. Details: $($_.Exception.Message)"
}

$manifest.result = 'PASS'
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
Write-Output "AuxiliaryArchive=PASS; Manifest=$manifestPath; Directories=$($entries.Count)"
