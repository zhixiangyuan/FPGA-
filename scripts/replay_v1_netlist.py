"""Independent delivery replay from local sealed VO/TB/lib/Golden inputs."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--reference',type=Path,default=ROOT/'evidence/netlist_001');ap.add_argument('--load-only',action='store_true');args=ap.parse_args();src=args.reference.resolve()
 s=json.loads((src/'summary.json').read_text());assert s['result']=='PASS' and s['exit_code']==0
 for x in s['sources']:assert sha(src/Path(x['path']).name)==x['snapshot_sha256']
 for n,h in json.loads((src/'golden/sha256.json').read_text()).items():assert sha(src/'golden'/n)==h
 i=1
 while (ROOT/f'runs/replay_{i:03d}').exists():i+=1
 run=ROOT/f'runs/replay_{i:03d}';run.mkdir(parents=True)
 for n in ('AFDX_top.vo','altera_primitives.v','220model.v','stratix_atoms.v','tb_v1_netlist.sv','v1_netlist_observer.vh'):shutil.copy2(src/n,run/n)
 shutil.copytree(src/'golden',run/'golden')
 ms=Path(os.environ.get('MODELSIM_BIN',r'D:\FPGA\Modlesim20.4\ModelSim20.4\win64'));shutil.copy2(ms.parent/'modelsim.ini',run/'modelsim.ini');os.chmod(run/'modelsim.ini',0o666)
 do=['onerror {quit -code 2 -force}','vlib work','vmap work work']
 for n in ('altera_primitives.v','220model.v','stratix_atoms.v','AFDX_top.vo','tb_v1_netlist.sv'):do.append(f'vlog {"-sv" if n.endswith(".sv") else ""} +incdir+{{{run.as_posix()}}} {{{(run/n).as_posix()}}}')
 do+=['vopt -O5 -inlineFactor=100 +acc=nr+tb_v1_netlist work.tb_v1_netlist -o replay_optimized','vsim -t 1ps -onfinish stop -wlf waves.wlf work.replay_optimized','log /tb_v1_netlist/reset /tb_v1_netlist/rx_data /tb_v1_netlist/rx_valid /tb_v1_netlist/tx_data /tb_v1_netlist/tx_valid','run 0ns' if args.load_only else 'run -all','quit -code 0 -force'];(run/'run.do').write_text('\n'.join(do)+'\n')
 env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(ms.parent/'LICENSE.TXT'))
 command=[str(ms/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do']
 with (run/'console.log').open('wb') as log:r=subprocess.run(command,cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=86400)
 text=(run/'transcript.log').read_text(errors='replace');passed=r.returncode==0 and '** Error' not in text and '** Fatal' not in text and ('Errors: 0' in text) and (args.load_only or 'V1_REAL_NETLIST = PASS' in text)
 out={'result':'PASS' if passed else 'FAIL','scope':'independent compile/elaboration/run-0ns only' if args.load_only else 'independent full real VO replay','full_clocked_suite_executed':not args.load_only,'exit_code':r.returncode,'source_reference':str(src),'local_compile_sources_only':True,'source_snapshot_sha256':{p.name:sha(p) for p in run.iterdir() if p.suffix in ('.vo','.v','.sv','.vh')},'command':command}
 (run/'summary.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2));return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
