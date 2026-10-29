"""Install small Chinese launchers/docs; never copies the production project."""
from pathlib import Path
import hashlib,json
from interactive_demo import DELIVERY,ROOT,TITLES

def main():
    DELIVERY.mkdir(parents=True,exist_ok=True)
    ps=r'''param([ValidateRange(1,10)][int]$Scenario=10)
$ErrorActionPreference='Stop'
$project='D:\FPGA\captain_integration'
$python='E:\ICAN\PYthon-3.10\python.exe'
$modelsim='D:\FPGA\Modlesim20.4\ModelSim20.4\win64\vsim.exe'
if ($env:MODELSIM_BIN) { $modelsim=Join-Path $env:MODELSIM_BIN 'vsim.exe' }
try {
 if (!(Test-Path -LiteralPath $python)) { throw "找不到 Python：$python" }
 if (!(Test-Path -LiteralPath $modelsim)) { throw "找不到 ModelSim：$modelsim" }
 if (!(Test-Path -LiteralPath "$project\sim\tb_interactive_demo.sv")) { throw '工程文件缺失，请恢复交付说明指定的 dev 版本。' }
 if ($Scenario -eq 9) {
   Start-Process -FilePath (Join-Path $env:WINDIR 'explorer.exe') -ArgumentList "$project\reports"
   Start-Process -FilePath (Join-Path $env:WINDIR 'explorer.exe') -ArgumentList "/select,`"$project\build\elinx\AFDXSUB_013\AFDXSUB.epr`""
   exit 0
 }
 & $python -c 'import tkinter'
 if ($LASTEXITCODE -ne 0) { throw 'Python 缺少 Tk，控制窗口无法启动。' }
 $logDir=Join-Path $PSScriptRoot '启动日志'
 New-Item -ItemType Directory -Path $logDir -Force | Out-Null
 $stamp=Get-Date -Format 'yyyyMMdd_HHmmss_fff'
 $script=Join-Path $project 'scripts\interactive_demo.py'
 $demoArgs=if ($Scenario -eq 10) { @('"'+$script+'"','--basic') } else { @('"'+$script+'"','--scenario',"$Scenario") }
 Start-Process -FilePath $python -ArgumentList $demoArgs -WorkingDirectory $project -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir "$stamp.out.log") -RedirectStandardError (Join-Path $logDir "$stamp.err.log")
 Write-Host '已启动。请等待中文控制窗口与 ModelSim；关键操作由本人完成。'
} catch {
 Write-Host "启动失败：$_" -ForegroundColor Red
 Read-Host '按 Enter 关闭'
 exit 1
}
'''
    (DELIVERY/'launch.ps1').write_text(ps,encoding='utf-8-sig')
    legacy=DELIVERY/'单项测试入口';legacy.mkdir(exist_ok=True)
    for i,title in enumerate(TITLES+['工程与综合报告证据'],1):
        name=f'{i:02d}_{title}演示.cmd';old=DELIVERY/name;target=legacy/name
        assert old.resolve().parent==DELIVERY.resolve() and target.resolve().parent==legacy.resolve()
        if old.exists() and not target.exists():old.replace(target)
        cmd=f'@echo off\r\n"%SystemRoot%\u005cSystem32\u005cWindowsPowerShell\u005cv1.0\u005cpowershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\\launch.ps1" -Scenario {i}\r\nif errorlevel 1 pause\r\n'
        target.write_bytes(cmd.encode('ascii',errors='strict'))
    for name,scenario in (('视频1_系统基础功能演示.cmd',10),('视频2_系统性能展示.cmd',7),('视频3_调度优化对照演示.cmd',8)):
        cmd=f'@echo off\r\n"%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch.ps1" -Scenario {scenario}\r\nif errorlevel 1 pause\r\n'
        (DELIVERY/name).write_bytes(cmd.encode('ascii'))
    for name in ('新手操作手册.md','三分钟讲解与录屏步骤.md','验证状态说明.md'):
        source=ROOT/'docs'/'interactive_demo'/name
        if source.exists():(DELIVERY/name).write_bytes(source.read_bytes())
    files=[p for p in DELIVERY.iterdir() if p.is_file() and p.name!='交付文件哈希.json']+list(legacy.glob('*.cmd'))
    (DELIVERY/'交付文件哈希.json').write_text(json.dumps({str(p.relative_to(DELIVERY)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(DELIVERY)

if __name__=='__main__':main()
