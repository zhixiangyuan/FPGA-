param([int]$Seconds=240)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$outputPath=Join-Path $taskRoot 'build\audit\stage2\gui_synthesis_processes.jsonl'
if(Test-Path -LiteralPath $outputPath){throw 'Preserve the existing monitor; choose a new record before retry.'}
$seenIds=@{}
$names=@('quartus_map.exe','quartus_cdb.exe','ehiway_map.exe','Implementation.exe','Infrastructure.exe','QInfrastructure.exe','eLinx_synthesis.exe')
$deadline=(Get-Date).AddSeconds($Seconds)
while((Get-Date)-lt $deadline){
 $items=Get-CimInstance Win32_Process | Where-Object {$_.Name -in $names}
 foreach($item in $items){
  if(!$seenIds.ContainsKey($item.ProcessId)){
   $seenIds[$item.ProcessId]=$true
   $record=@{time=(Get-Date).ToString('o');name=$item.Name;pid=$item.ProcessId;path=$item.ExecutablePath;command=$item.CommandLine}
   $record | ConvertTo-Json -Compress | Add-Content -LiteralPath $outputPath -Encoding UTF8
  }
 }
 Start-Sleep -Milliseconds 500
}
Write-Output "Read-only synthesis process records: $outputPath"
