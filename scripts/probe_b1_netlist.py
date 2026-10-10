from pathlib import Path
import shutil,subprocess,os,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
MS=Path(r'D:\FPGA\Modlesim20.4\ModelSim20.4\win64')
SRC=ROOT/'runs/netlist_002'
OUT=ROOT/'runs/netlist_probe_001'
OUT.mkdir()
inputs=[SRC/n for n in ['altera_primitives.v','220model.v','stratix_atoms.v','afdx_network_tx_top.vo','tb_b1_netlist_loopback.sv']]
for p in inputs:shutil.copy2(p,OUT/p.name)
shutil.copytree(SRC/'golden',OUT/'golden')
shutil.copy2(SRC/'modelsim.ini',OUT/'modelsim.ini')
lines=['onerror {quit -code 2 -force}','onbreak {quit -code 5 -force}','vlib work','vmap work work']
for p in inputs:lines.append(f"vlog {'-sv +define+DUT_IS_NETLIST ' if p.suffix=='.sv' else ''}-work work {{{(OUT/p.name).as_posix()}}}")
lines+=['vsim -t 1ps -voptargs=+acc=npr+tb_b1_netlist_loopback work.tb_b1_netlist_loopback','run 1 us','puts "NETLIST_TIME_ADVANCE_PROBE = PASS time=[now]"','quit -code 0 -force']
(OUT/'run.do').write_text('\n'.join(lines)+'\n',encoding='utf-8')
env=os.environ.copy();env['MGLS_LICENSE_FILE']=str(MS.parent/'LICENSE.TXT')
cmd=[str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do']
r=subprocess.run(cmd,cwd=OUT,env=env,capture_output=True,timeout=60)
(OUT/'console.log').write_bytes(r.stdout+r.stderr)
t=(OUT/'transcript.log').read_text(errors='replace')
data={'result':'PASS' if r.returncode==0 and 'NETLIST_TIME_ADVANCE_PROBE = PASS' in t else 'FAIL','scope':'1us simulation-time advance diagnostic only; not a functional acceptance','exit':r.returncode,'inputs':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in inputs]}
(OUT/'summary.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
print(t[-2500:]);print(data['result'])
