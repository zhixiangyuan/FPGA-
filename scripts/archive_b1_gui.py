from pathlib import Path
import shutil,json,hashlib,re
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'runs/elinx_001/AFDXNetwork'
OUT=ROOT/'evidence/gui_success_001'
if OUT.exists():raise SystemExit('Archive exists; use a new numbered archive rather than overwrite')
OUT.mkdir(parents=True)
shutil.copytree(SRC,OUT/'AFDXNetwork')
shot=Path(r'C:\Users\袁志祥\AppData\Local\Temp\codex-clipboard-4dd10556-7ba4-4217-a881-a68336c9dac0.png')
if shot.exists():shutil.copy2(shot,OUT/'gui_synthesis_complete.png')
files=[]
for p in sorted((OUT/'AFDXNetwork').rglob('*')):
    if p.is_file():
        origin=SRC/p.relative_to(OUT/'AFDXNetwork')
        h=hashlib.sha256(p.read_bytes()).hexdigest()
        assert h==hashlib.sha256(origin.read_bytes()).hexdigest(),str(origin)
        files.append({'original':str(origin),'archive':str(p),'bytes':p.stat().st_size,'sha256':h})
(OUT/'artifact_hashes.json').write_text(json.dumps(files,indent=2),encoding='utf-8')
report=SRC/'AFDXNetwork.runs/synth_1/AFDXNetwork.map.rpt'
t=report.read_text(errors='replace')
warnings=[{'code':code,'message':message.strip()} for code,message in re.findall(r'^\s*Warning \((\d+)\): (.*)$',t,re.M)]
assert len(warnings)==18,len(warnings)
(OUT/'warnings.json').write_text(json.dumps(warnings,indent=2),encoding='utf-8')
rows=[line for line in t.splitlines() if any(s in line for s in ('|afdx_single_vl_tx:sender|','|afdx_bag_gate:bag_gate|','|afdx_ipv4_checksum:checksum_q|','|mac_gmii_core:mac|','|mac_gmii_rx:rx|','|mac_gmii_tx:tx|'))]
(OUT/'retained_hierarchy.txt').write_text('\n'.join(rows),encoding='utf-8')
print('GUI_SYNTHESIS_ARCHIVE = PASS files='+str(len(files)))
print('WARNINGS = '+str(len(warnings)))
print('ARCHIVE = '+str(OUT))
