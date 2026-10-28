"""Compile the full candidate once and reuse it for two short acceptance tops."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,os,shutil,subprocess,csv
from run_competition import ROOT,MS,sources,sha
import run_competition_smoke as smoke
import run_management_netlist as mgmt
from generate_stage2_mgmt_golden import afdx_frame,ES_MAC,MANAGER_MAC,ES_IP,MANAGER_IP
from generate_snmp_golden import message,oid,tlv
from frozen_frame_reference import wire_for
from modelsim_support import prepare_ini

def generate(run):
 expected=mgmt.generate(run/'mgolden');g=run/'mgolden'
 stim=(g/'stimulus.vh').read_text().splitlines();(g/'stimulus.vh').write_text('\n'.join(stim[:4]+stim[5:])+'\n')
 blob=bytes.fromhex(''.join((g/'fixtures.mem').read_text().split()))
 req=message(0xa0,3,b'public',[(oid(4),tlv(5,b''))])
 wire=wire_for(afdx_frame(bytes.fromhex('0300000012b4'),MANAGER_MAC,MANAGER_IP,ES_IP,49152,161,req,1))
 (g/'fixtures.mem').write_text(''.join(f'{x:02x}\n' for x in blob+wire))
 (g/'constants.vh').write_text(f'localparam RX_BYTES={len(blob)+len(wire)},GET_OFFSET={len(blob)},GET_LENGTH={len(wire)};\n')
 expected[0x12b4][1]=wire_for(afdx_frame(bytes.fromhex('0300000012b4'),ES_MAC,ES_IP,MANAGER_IP,161,49152,message(0xa2,3,b'public',[(oid(4),tlv(4,b'afdx-es-team3'))]),1))
 (g/'expected.json').write_text(json.dumps({str(k):[x.hex() for x in v] for k,v in expected.items()},indent=2))
 return expected

def main():
 p=argparse.ArgumentParser();p.add_argument('--vo',type=Path);p.add_argument('--provenance',type=Path);p.add_argument('--rtl-reference',type=Path);a=p.parse_args()
 family='acceptance_short_vo' if a.vo else 'acceptance_short_rtl';i=1
 while (ROOT/f'build/logs/{family}_{i:03d}').exists():i+=1
 run=ROOT/f'build/logs/{family}_{i:03d}';run.mkdir(parents=True)
 exp,wires=smoke.generate(run/'golden');mexp=generate(run)
 tbs=[ROOT/'sim/tb_competition_smoke.sv',ROOT/'sim/tb_acceptance_management_short.sv']
 helpers=[Path(__file__),ROOT/'scripts/run_competition.py',ROOT/'scripts/run_competition_smoke.py',ROOT/'scripts/run_management_netlist.py',ROOT/'scripts/generate_stage2_mgmt_golden.py',ROOT/'scripts/generate_snmp_golden.py',ROOT/'scripts/frozen_frame_reference.py',ROOT/'scripts/modelsim_support.py']
 inputs={str(x.relative_to(ROOT)):sha(x) for x in sources()+tbs+helpers}
 golden={str(x.relative_to(run)):sha(x) for d in ['golden','mgolden'] for x in (run/d).iterdir()}
 if a.vo:
  export=json.loads(a.provenance.read_text());assert export['result']=='PASS' and sha(a.vo)==export['delivered_netlist_sha256']
  project=Path(export['source_project']);manifest=json.loads((project/'project_manifest.json').read_text());assert sha(project/'project_manifest.json')==export['source_manifest_sha256']
  for row in manifest['sources']:assert sha(ROOT/row['canonical_source'])==row['sha256']==sha(project/row['snapshot'])
  ref=json.loads((a.rtl_reference/'summary.json').read_text());assert ref['result']=='PASS' and ref['inputs']==inputs and ref['golden']==golden
  compiled=[ROOT/'build/logs/netlist_001'/n for n in ['altera_primitives.v','220model.v','stratix_atoms.v']]+[a.vo.resolve()]+tbs
 else:compiled=sources()+tbs
 for x in set(sources()+tbs+helpers+compiled):shutil.copy2(x,run/x.name)
 prepare_ini(run,MS)
 commands=['onerror {quit -code 2 -force}','vlib work']+[f'vlog {"-sv " if x.suffix==".sv" else ""}{x.name}' for x in compiled]
 commands+=['vopt -O5 work.tb_competition_smoke -o smoke_opt','vsim -onfinish stop -t 1ps work.smoke_opt','run -all','quit -sim','vopt -O5 work.tb_acceptance_management_short -o management_short_opt','vsim -onfinish stop -t 1ps work.management_short_opt','run -all','quit -code 0 -force']
 (run/'run.do').write_text('\n'.join(commands)+'\n')
 proof=dict(result='RUNNING',backend='VO' if a.vo else 'RTL',inputs=inputs,golden=golden,compiled={str(x):sha(x) for x in compiled},clock_ns=8,BAG_cycles=125000,started_utc=datetime.now(timezone.utc).isoformat(),long_VO_persistence_BAG_capacity_performance='NOT RUN; covered separately by full RTL',full_netlist_compile_count=1)
 if a.vo:proof.update(provenance_sha256=sha(a.provenance),rtl_reference_sha256=sha(a.rtl_reference/'summary.json'))
 path=run/'summary.json';path.write_text(json.dumps(proof,indent=2));env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'))
 print('ACCEPTANCE_SHORT_RUN',run,flush=True)
 with (run/'console.log').open('wb') as log:
  proc=subprocess.Popen([str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do'],cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT);proof['pid']=proc.pid;path.write_text(json.dumps(proof,indent=2));code=proc.wait(timeout=14400)
 text=(run/'transcript.log').read_text(errors='replace');passed=code==0 and 'COMPETITION_SMOKE_PASS' in text and 'ACCEPTANCE_MANAGEMENT_SHORT_PASS' in text and '** Error' not in text and '** Fatal' not in text;error=None;evidence={}
 if passed:
  try:
   evidence=smoke.verify(run,exp,wires)
   actual=bytes.fromhex(''.join((run/'network_tx.mem').read_text().split()));events=list(csv.DictReader((run/'frames.csv').open()))
   assert len(events)==3
   for row in events:
    vl=int(row['vl']);size=int(row['bytes']);assert actual[:size]==mexp[vl].pop(0);actual=actual[size:]
   assert not actual and all(not x for x in mexp.values())
   assert all(sha(ROOT/n)==h for n,h in inputs.items()) and all(sha(Path(n))==h for n,h in proof['compiled'].items())
   assert all(sha(run/n)==h for n,h in golden.items())
   evidence.update(SNMP_SET=True,SNMP_GET_independent_reset=True,SNTP_sync=True,CRC_IP_UDP_rejection=True)
  except Exception as exc:passed=False;error=repr(exc)
 proof.update(result='PASS' if passed else 'FAIL',error=error,exit_code=code,evidence=evidence,completed_utc=datetime.now(timezone.utc).isoformat());path.write_text(json.dumps(proof,indent=2));print(text[-1800:]);print(json.dumps({k:v for k,v in proof.items() if k not in ('inputs','golden','compiled')},indent=2));return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())

