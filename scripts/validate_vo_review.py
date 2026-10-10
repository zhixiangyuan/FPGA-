from pathlib import Path
import ast,hashlib,json,subprocess,shutil
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evidence'/'official_vo_20230605'/'tb_compile_001'
OUT.mkdir(parents=True,exist_ok=False)
MS=Path(r'D:\FPGA\Modlesim20.4\ModelSim20.4\win64')
TB=ROOT/'sim'/'tb_b1_netlist_loopback.sv'
runner=ROOT/'scripts'/'run_b1_netlist.py'
exporter=ROOT/'scripts'/'export_b1_functional_netlist.py'
for path in (runner,exporter):ast.parse(path.read_text(encoding='utf-8'),filename=str(path))
assert '+define+DUT_IS_NETLIST' in runner.read_text(encoding='utf-8')
assert '`ifdef DUT_IS_NETLIST' in TB.read_text(encoding='utf-8')
snap=OUT/TB.name;shutil.copy2(TB,snap)
results=[]
for cmd in ([str(MS/'vlib.exe'),'work'],[str(MS/'vlog.exe'),'-sv','+define+DUT_IS_NETLIST','-work','work',str(snap)]):
    r=subprocess.run(cmd,cwd=OUT,capture_output=True,timeout=60)
    results.append({'command':cmd,'exit':r.returncode,'output':(r.stdout+r.stderr).decode(errors='replace')})
(OUT/'compile.log').write_text('\n'.join(x['output'] for x in results),encoding='utf-8')
passed=all(x['exit']==0 for x in results)
manifest=ROOT/'runs'/'elinx_001'/'project_manifest.json'
m=json.loads(manifest.read_text(encoding='utf-8'))
for row in m['source_manifest']:
    for key,hash_key in (('snapshot','snapshot_sha256'),('original','original_sha256')):
        assert hashlib.sha256(Path(row[key]).read_bytes()).hexdigest()==row[hash_key]
data={'result':'PASS' if passed else 'FAIL','scope':'Compile-only verification of the netlist TB macro branch; no simulation, no netlist PASS, no synthesis or Implementation','commands':results,'source_manifest_unchanged':True,'files':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in (TB,runner,exporter,manifest)]}
(OUT/'validation.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print('NETLIST_TB_MACRO_COMPILE_ONLY = '+data['result'])
print('B0_B1_PROJECT_SOURCE_HASHES = UNCHANGED')
print('B1_NETLIST_FUNCTIONAL_SIM = NOT RUN')
raise SystemExit(0 if passed else 1)
