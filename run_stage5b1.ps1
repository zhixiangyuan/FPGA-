param()
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$python = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = (Get-Command python.exe -ErrorAction Stop).Source }
$b0 = 'D:\FPGA\captain_integration\stage5B0_selfmac_20261010'
$pwsh = (Get-Command pwsh.exe -ErrorAction Stop).Source

$index = 1
while (Test-Path -LiteralPath (Join-Path $root ('runs\acceptance_{0:D3}' -f $index))) { $index++ }
$run = Join-Path $root ('runs\acceptance_{0:D3}' -f $index)
New-Item -ItemType Directory -Path $run | Out-Null
$states = [ordered]@{}
$evidence = [ordered]@{}

function Invoke-Step([string]$Name, [string]$Exe, [string[]]$ArgList, [string]$Cwd) {
    $log = Join-Path $run ($Name + '.log')
    Push-Location $Cwd
    try {
        $output = & $Exe @ArgList 2>&1
        $code = $LASTEXITCODE
    } finally { Pop-Location }
    $output | Set-Content -LiteralPath $log -Encoding utf8
    $output | ForEach-Object { Write-Host $_ }
    $states[$Name] = if ($code -eq 0) { 'PASS' } else { 'FAIL' }
    Write-Host ($Name + ' = ' + $states[$Name])
    return $code
}

$failure = $false
foreach ($step in @(
    @{ Name='b1_ready_stall'; Script='scripts\run_b1_ready_stall.py' },
    @{ Name='b1_real_gmii'; Script='scripts\run_b1_gmii_loopback.py' },
    @{ Name='b1_125m_rtl'; Script='scripts\run_b1_125m_rtl.py' },
    @{ Name='b0_abort_contract'; Script='scripts\run_b0_abort_contract.py' }
)) {
    if ((Invoke-Step $step.Name $python @('-B', (Join-Path $root $step.Script)) $root) -ne 0) { $failure = $true }
}

if ((Invoke-Step 'stage5b0_full_regression' $pwsh @('-NoLogo','-NoProfile','-File',(Join-Path $b0 'run_acceptance.ps1')) $b0) -ne 0) { $failure = $true }

$b1LatestGmii = Get-ChildItem -LiteralPath (Join-Path $root 'runs') -Directory -Filter 'gmii_*' | Sort-Object Name -Descending | Select-Object -First 1
$b1LatestStall = Get-ChildItem -LiteralPath (Join-Path $root 'runs') -Directory -Filter 'stall_*' | Sort-Object Name -Descending | Select-Object -First 1
$b1LatestAbort = Get-ChildItem -LiteralPath (Join-Path $root 'runs') -Directory -Filter 'abort_*' | Sort-Object Name -Descending | Select-Object -First 1
if ($b1LatestGmii) { $evidence['b1_gmii'] = $b1LatestGmii.FullName; $states['B1_GMII'] = (Get-Content -LiteralPath (Join-Path $b1LatestGmii.FullName 'summary.json') -Raw | ConvertFrom-Json).result }
if ($b1LatestStall) { $evidence['b1_ready_stall'] = $b1LatestStall.FullName; $states['B1_READY_STALL'] = (Get-Content -LiteralPath (Join-Path $b1LatestStall.FullName 'summary.json') -Raw | ConvertFrom-Json).result }
if ($b1LatestAbort) { $evidence['b0_abort'] = $b1LatestAbort.FullName; $states['B0_ABORT_RECOVERY'] = (Get-Content -LiteralPath (Join-Path $b1LatestAbort.FullName 'summary.json') -Raw | ConvertFrom-Json).result }
$states['B1_125M_RTL'] = $states['b1_125m_rtl']
$evidence['b1_125m_rtl'] = (Get-ChildItem -LiteralPath (Join-Path $root 'runs') -Directory -Filter 'clk125_*' | Sort-Object Name -Descending | Select-Object -First 1).FullName

$b0SummaryPath = Join-Path $b0 'summary.json'
if (Test-Path -LiteralPath $b0SummaryPath) {
    $b0Summary = Get-Content -LiteralPath $b0SummaryPath -Raw | ConvertFrom-Json
    foreach ($key in @('STAGE1_REGRESSION','STAGE2_REGRESSION','STAGE3B2_RESULT','SELF_MAC_STAGE5B0_RESULT','SELF_MAC_POST_SYNTH_FUNCTIONAL_SIM','ORIGINAL_PRODUCTION_UNCHANGED')) { $states[$key] = $b0Summary.states.$key }
    $evidence['stage5b0_summary'] = $b0SummaryPath
    $evidence['stage3b2_run'] = $b0Summary.evidence.historical_regression
    $evidence['stage5b0_run'] = $b0Summary.evidence.rtl
    $evidence['stage5b0_netlist_run'] = $b0Summary.evidence.netlist
}
$states['POST_SYNTH_TIMING'] = 'NOT VERIFIED'
$states['EQ6_NATIVE_NETLIST_EQUIVALENCE'] = 'NOT VERIFIED'
& $python -B (Join-Path $root 'scripts\write_current_status.py')
if ($LASTEXITCODE -ne 0) { throw 'Cannot derive status from the actual synthesis/netlist/regression evidence.' }
$current = Get-Content -LiteralPath (Join-Path $root 'runs\current_status.json') -Raw | ConvertFrom-Json
$states['ELINX_B1_SYNTHESIS'] = $current.states.B1_ELINX_SYNTHESIS
$states['B1_NETLIST_FUNCTIONAL_SIM'] = $current.states.B1_POST_SYNTH_FUNCTIONAL_SIM
$states['CSG225_DIAGNOSTIC_TOP_IO_FIT'] = $current.states.CSG225_DIAGNOSTIC_TOP_IO_FIT
$states['STAGE5B1_RESULT'] = if ($failure -or @($states.Values | Where-Object { $_ -eq 'FAIL' }).Count -gt 0) { 'FAIL' } else { $current.states.STAGE5B1_RESULT }

$summary = [ordered]@{ run=$run; states=$states; evidence=$evidence; scope='B1 single-VL TX RTL and actual B0 MAC/GMII functional validation plus Stage1/2/3-B2/B0 regressions; no Implementation/Bitstream/hardware download' }
$summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $run 'summary.json') -Encoding utf8
$summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $root 'summary.json') -Encoding utf8
Write-Output ('STAGE5B1_RESULT = ' + $states['STAGE5B1_RESULT'])
if ($states['STAGE5B1_RESULT'] -eq 'FAIL' -or $states['STAGE5B1_RESULT'] -eq 'BLOCKED') { exit 1 }
