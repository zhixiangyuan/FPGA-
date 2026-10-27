"""Full receive chain: all 4096 VLs, both networks, two distinct SNs per VL."""
from datetime import datetime,timezone
from pathlib import Path
import csv,json,os,shutil,subprocess
from run_competition import ROOT,MS,sources,sha
from frozen_frame_reference import make_client,wire_for
from modelsim_support import prepare_ini

def main():
    i=1
    while (ROOT/f'build/logs/rx_capacity_{i:03d}').exists():i+=1
    run=ROOT/f'build/logs/rx_capacity_{i:03d}';run.mkdir(parents=True);out=run/'golden';out.mkdir()
    wire=bytearray();expected=[]
    for turn in range(2):
        for n in range(4096):
            vl=0x1234+n;frame,data=make_client(n+turn*4097,1,turn+1)
            frame=frame[:4]+vl.to_bytes(2,'big')+frame[6:];w=wire_for(frame);assert len(w)==72
            wire.extend(w);expected.append(vl.to_bytes(2,'big')+data)
    (out/'wire.mem').write_text(''.join(f'{b:02x}\n' for b in wire))
    (out/'constants.vh').write_text(f'localparam WIRE_BYTES={len(wire)};\n')
    (out/'expected.json').write_text(json.dumps([p.hex() for p in expected])+'\n')
    files=sources()+[ROOT/'sim/tb_rx_capacity.sv']
    inputs=files+[Path(__file__),ROOT/'scripts/run_competition.py',ROOT/'scripts/frozen_frame_reference.py',ROOT/'scripts/modelsim_support.py']
    for x in inputs:shutil.copy2(x,run/x.name)
    prepare_ini(run,MS)
    cmd=['onerror {quit -code 2 -force}','vlib work']+[f'vlog {"-sv " if x.suffix==".sv" else ""}{x.name}' for x in files]
    cmd+=['vopt -O5 work.tb_rx_capacity -o capacity_opt','vsim -t 1ps work.capacity_opt','run -all','quit -code 0 -force']
    (run/'run.do').write_text('\n'.join(cmd)+'\n')
    proof=dict(result='RUNNING',started_utc=datetime.now(timezone.utc).isoformat(),clock_ns=8,
               inputs={str(x.relative_to(ROOT)):sha(x) for x in inputs},golden={x.name:sha(x) for x in out.iterdir()})
    path=run/'summary.json';path.write_text(json.dumps(proof,indent=2)+'\n')
    env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'));print(f'RX_CAPACITY_RUN {run}',flush=True)
    with (run/'console.log').open('wb') as log:
        code=subprocess.run([str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do'],cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1800).returncode
    text=(run/'transcript.log').read_text(errors='replace');passed=code==0 and 'RX_CAPACITY_PASS' in text and '** Error' not in text and '** Fatal' not in text
    error=None
    if passed:
        try:
            actual=[];data=bytearray()
            for r in csv.DictReader((run/'application.csv').open()):
                if int(r['sop']):assert not data
                data.append(int(r['data']))
                if int(r['eop']):actual.append(bytes(data));data.clear()
            assert not data and actual==expected,'full-chain per-VL delivery mismatch'
            assert all(sha(ROOT/n)==h for n,h in proof['inputs'].items())
        except Exception as e:passed=False;error=repr(e)
    proof.update(result='PASS' if passed else 'FAIL',error=error,exit_code=code,
                 configured_RX_VLs=4096,wire_frames_per_network=8192,application_deliveries=8192,
                 source='real GMII wire including preamble/SFD/FCS',both_networks=True,
                 completed_utc=datetime.now(timezone.utc).isoformat())
    path.write_text(json.dumps(proof,indent=2)+'\n');print(text[-1300:]);print(json.dumps({k:v for k,v in proof.items() if k not in ('inputs','golden')},indent=2))
    return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
