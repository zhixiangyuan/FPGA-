"""Pipelined builder: real BAG, 254->255->1, independent VLs and abort."""
from datetime import datetime,timezone
from pathlib import Path
import csv,json,os,shutil,subprocess
from run_competition import ROOT,MS,sha
from frozen_frame_reference import make_client,wire_for
from modelsim_support import prepare_ini

def main():
    i=1
    while (ROOT/f'build/logs/pipelined_sender_{i:03d}').exists():i+=1
    run=ROOT/f'build/logs/pipelined_sender_{i:03d}';run.mkdir(parents=True)
    expected=[]
    for cid,vl,n,sn in [(0,0x1234,64,254),(1,0x1235,1471,254),(2,0x1234,1,255),(3,0x1234,512,1),(4,0x1234,1,2),(5,0x1234,1471,3)]:
        frame,_=make_client(cid,n,sn);frame=frame[:4]+vl.to_bytes(2,'big')+frame[6:];expected.append(wire_for(frame))
    (run/'expected.json').write_text(json.dumps([w.hex() for w in expected])+'\n')
    files=[ROOT/'vendor/frozen'/n for n in ('afdx_byte_fifo.v','mac_frame_store.v','mac_crc32_byte.v','afdx_bag_gate.v','afdx_ipv4_checksum.v','mac_gmii_tx.v')]
    files+=[ROOT/'rtl/afdx_multi_vl_tx.v',ROOT/'rtl/afdx_mac_tx_stream.v',ROOT/'sim/tb_pipelined_sender.sv']
    inputs=files+[Path(__file__),ROOT/'scripts/frozen_frame_reference.py',ROOT/'scripts/modelsim_support.py']
    for f in inputs:shutil.copy2(f,run/f.name)
    prepare_ini(run,MS)
    cmd=['onerror {quit -code 2 -force}','vlib work']+[f'vlog {"-sv " if f.suffix==".sv" else ""}{f.name}' for f in files]
    cmd+=['vopt -O5 work.tb_pipelined_sender -o sender_opt','vsim -t 1ps work.sender_opt','run -all','quit -code 0 -force']
    (run/'run.do').write_text('\n'.join(cmd)+'\n');proof=dict(result='RUNNING',started_utc=datetime.now(timezone.utc).isoformat(),
        clock_ns=8,BAG_cycles=125000,inputs={str(f.relative_to(ROOT)):sha(f) for f in inputs},expected_sha256=sha(run/'expected.json'))
    path=run/'summary.json';path.write_text(json.dumps(proof,indent=2)+'\n')
    env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'))
    with (run/'console.log').open('wb') as log:
        code=subprocess.run([str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do'],cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600).returncode
    text=(run/'transcript.log').read_text(errors='replace');ok=code==0 and 'PIPELINED_SENDER_PASS' in text and '** Error' not in text and '** Fatal' not in text;error=None
    if ok:
        try:
            assert bytes.fromhex(''.join((run/'wire.mem').read_text().split()))==b''.join(expected)
            rows=list(csv.DictReader((run/'events.csv').open()));assert len(rows)==6;previous={};gaps=[]
            for row in rows:
                vl=int(row['vl']);start=int(row['start'])
                if vl in previous:gaps.append(start-previous[vl]);assert start-previous[vl]>=125000
                previous[vl]=start
            assert all(sha(ROOT/n)==h for n,h in proof['inputs'].items())
        except Exception as exc:ok=False;error=repr(exc)
    proof.update(result='PASS' if ok else 'FAIL',exit_code=code,error=error,completed_utc=datetime.now(timezone.utc).isoformat())
    path.write_text(json.dumps(proof,indent=2)+'\n');print(text[-950:]);print(json.dumps({k:v for k,v in proof.items() if k!='inputs'},indent=2))
    return 0 if ok else 1

if __name__=='__main__':raise SystemExit(main())
