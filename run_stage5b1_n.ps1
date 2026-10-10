param()
$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$taskPython=Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$taskPwsh=(Get-Command pwsh.exe -ErrorAction Stop).Source
$index=1
while(Test-Path -LiteralPath (Join-Path $root ('runs\n_acceptance_{0:D3}' -f $index))){$index++}
$run=Join-Path $root ('runs\n_acceptance_{0:D3}' -f $index)
New-Item -ItemType Directory -Path $run | Out-Null
function Run-Step([string]$Name,[string]$Exe,[string[]]$ArgList){
    $out=& $Exe @ArgList 2>&1
    $code=$LASTEXITCODE
    $out | Set-Content -LiteralPath (Join-Path $run ($Name+'.log')) -Encoding utf8
    $out | ForEach-Object {Write-Host $_}
    if($code -ne 0){throw ($Name+' failed; preserve and inspect '+$run)}
}
Push-Location $root
try{
    # Synthesis must already have completed in the official GUI. This entry
    # never launches Synthesis, Implementation, Bitstream or hardware download.
    Run-Step 'rtl_and_history' $taskPwsh @('-NoProfile','-File',(Join-Path $root 'run_stage5b1.ps1'))
    Run-Step 'synthesis_preflight' $taskPython @('-B',(Join-Path $root 'scripts\export_b1_functional_netlist.py'),'--check-only')
    Run-Step 'functional_export' $taskPython @('-B',(Join-Path $root 'scripts\export_b1_functional_netlist.py'))
    $export=Get-ChildItem -LiteralPath (Join-Path $root 'runs') -Directory -Filter 'eda_export_*' | Sort-Object Name -Descending | Select-Object -First 1
    $model=Join-Path $export.FullName 'afdx_network_tx_top.vo'
    Run-Step 'real_netlist_full' $taskPython @('-B',(Join-Path $root 'scripts\run_b1_netlist.py'),$model,'--suite','full')
    Run-Step 'derive_result' $taskPython @('-B',(Join-Path $root 'scripts\write_current_status.py'))
    Copy-Item -LiteralPath (Join-Path $root 'runs\current_status.json') -Destination (Join-Path $run 'summary.json')
    $status=Get-Content -LiteralPath (Join-Path $run 'summary.json') -Raw | ConvertFrom-Json
    if($status.states.STAGE5B1_RESULT -notin @('PENDING_CAPTAIN_REVIEW','PASS')){throw 'Stage5B1 functional acceptance is incomplete; inspect separate statuses.'}
    Write-Host ('STAGE5B1_RESULT = '+$status.states.STAGE5B1_RESULT+'; evidence='+$run)
    Write-Host ('CSG225_DIAGNOSTIC_TOP_IO_FIT = '+$status.states.CSG225_DIAGNOSTIC_TOP_IO_FIT)
    Write-Host 'POST_SYNTH_TIMING = NOT VERIFIED'
    Write-Host 'EQ6_NATIVE_NETLIST_EQUIVALENCE = NOT VERIFIED'
}finally{Pop-Location}
