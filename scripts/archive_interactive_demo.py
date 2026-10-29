"""Archive selected PASS evidence without changing any existing result folder."""
from datetime import datetime
from pathlib import Path
import json,shutil
from interactive_demo import ROOT,DELIVERY,dump,sha

def main():
    reports=[ROOT/'reports/交互演示自检.json',ROOT/'reports/交互演示实现验证.json']
    runs=set()
    def collect(obj):
        if isinstance(obj,dict):
            if obj.get('result')=='PASS' and obj.get('run'):runs.add(Path(obj['run']))
            for value in obj.values():collect(value)
        elif isinstance(obj,list):
            for value in obj:collect(value)
    for p in reports:collect(json.loads(p.read_text(encoding='utf-8')))
    ui_report=ROOT/'reports/交互演示界面验证.json'
    if ui_report.exists():reports.append(ui_report);collect(json.loads(ui_report.read_text(encoding='utf-8')))
    archive=Path(r'D:\FPGA\AFDX_archive')/('interactive_demo_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    archive.mkdir(parents=True)
    for run in sorted(runs):
        assert json.loads((run/'verification.json').read_text(encoding='utf-8'))['result']=='PASS'
        target=archive/'runs'/run.name;target.mkdir(parents=True)
        for p in run.iterdir():
            if p.is_file() and (p.suffix.lower() in ('.csv','.json','.log','.wlf','.v','.sv','.py','.tcl','.ini','.do') or p.name.startswith('cmd_')):
                shutil.copy2(p,target/p.name)
    for p in reports:
        target=archive/'reports'/p.name;target.parent.mkdir(exist_ok=True);shutil.copy2(p,target)
    for p in DELIVERY.iterdir():
        if p.is_file():
            target=archive/'delivery'/p.name;target.parent.mkdir(exist_ok=True);shutil.copy2(p,target)
    manifest={str(p.relative_to(archive)):sha(p) for p in sorted(archive.rglob('*')) if p.is_file()}
    dump(archive/'sha256.json',manifest)
    assert all(sha(archive/p)==h for p,h in manifest.items())
    proof=dict(result='PASS',archive=str(archive),runs=len(runs),files=len(manifest),manifest_sha256=sha(archive/'sha256.json'))
    dump(ROOT/'reports/交互演示归档.json',proof);print(json.dumps(proof,ensure_ascii=False))

if __name__=='__main__':main()
