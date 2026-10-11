param()
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$base='D:\FPGA\captain_integration'
$b1=Join-Path $base 'stage5B1_single_vl_20261010'
$b0=Join-Path $base 'stage5B0_selfmac_20261010'
$index=1
while(Test-Path -LiteralPath (Join-Path $root ('runs\history_{0:D3}' -f $index))){$index++}
$run=Join-Path $root ('runs\history_{0:D3}' -f $index)
New-Item -ItemType Directory -Path $run -Force | Out-Null
$protected=@(
    (Join-Path $b1 'runs\current_status.json'),
    (Join-Path $b1 'summary.json'),
    (Join-Path $b0 'summary.json')
)
$backups=@()
foreach($p in $protected){
    if(Test-Path -LiteralPath $p){
        $backup=Join-Path $run ('before_'+$backups.Count+'.json')
        Copy-Item -LiteralPath $p -Destination $backup
        $backups+=@{Path=$p;Backup=$backup;Hash=(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash}
    }
}
$code=1
try{
    $pwsh=(Get-Command pwsh.exe -ErrorAction Stop).Source
    $output=& $pwsh -NoLogo -NoProfile -File (Join-Path $b1 'run_stage5b1.ps1') 2>&1
    $code=$LASTEXITCODE
    $output | Set-Content -LiteralPath (Join-Path $run 'console.log') -Encoding utf8
}finally{
    foreach($item in $backups){Copy-Item -LiteralPath $item.Backup -Destination $item.Path -Force}
}
$restored=$true
foreach($item in $backups){
    if((Get-FileHash -LiteralPath $item.Path -Algorithm SHA256).Hash -ne $item.Hash){$restored=$false}
}
$b1latest=Get-ChildItem -LiteralPath (Join-Path $b1 'runs') -Directory -Filter 'acceptance_*' | Sort-Object Name -Descending | Select-Object -First 1
$b0latest=Get-ChildItem -LiteralPath (Join-Path $b0 'runs') -Directory -Filter 'acceptance_*' | Sort-Object Name -Descending | Select-Object -First 1
$s3latest=Get-ChildItem -LiteralPath (Join-Path $base 'stage3B2_20261008\runs') -Directory -Filter 'run_*' | Sort-Object Name -Descending | Select-Object -First 1
$states=[ordered]@{exit_code=$code;protected_files_restored=$restored;b1_acceptance=$b1latest.FullName;b0_acceptance=$b0latest.FullName;stage3b2_regression=$s3latest.FullName}
$states | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $run 'summary.json') -Encoding utf8
Write-Output ('B2_HISTORY_RUN='+$run)
Write-Output ('EXIT_CODE='+$code)
Write-Output ('PROTECTED_FILES_RESTORED='+$restored)
Write-Output ('B1_ACCEPTANCE='+$b1latest.FullName)
Write-Output ('B0_ACCEPTANCE='+$b0latest.FullName)
Write-Output ('STAGE3B2_REGRESSION='+$s3latest.FullName)
if($code -ne 0 -or !$restored){exit 1}
