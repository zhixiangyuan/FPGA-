"""Real builder/MAC, eight legal BAG values, real clock without timer scaling."""
from pathlib import Path
from datetime import datetime,timezone
import csv,json,os,shutil,subprocess
from run_competition import ROOT,MS,sha
from frozen_frame_reference import make_client,wire_for
from modelsim_support import prepare_ini

def main():
    i=1
    while (ROOT/f'build/logs/bag_profiles_{i:03d}').exists():i+=1
    run=ROOT/f'build/logs/bag_profiles_{i:03d}';run.mkdir(parents=True)
    files=[ROOT/'vendor/frozen'/n for n in ('afdx_bag_gate.v','afdx_ipv4_checksum.v','mac_gmii_tx.v','mac_frame_store.v','afdx_byte_fifo.v','mac_crc32_byte.v')]
    files += [ROOT/'rtl/afdx_multi_vl_tx.v',ROOT/'sim/tb_bag_profiles.sv']
    inputs=files+[Path(__file__),ROOT/'scripts/frozen_frame_reference.py',ROOT/'scripts/modelsim_support.py']
    for x in inputs:shutil.copy2(x,run/x.name)
    expected=b''.join(wire_for(make_client(cid,1,1+cid%2)[0]) for cid in range(16))
    (run/'expected.mem').write_text(''.join(f'{b:02x}\n' for b in expected));prepare_ini(run,MS)
    cmd=['onerror {quit -code 2 -force}','vlib work']+[f'vlog {"-sv " if x.suffix==".sv" else ""}{x.name}' for x in files]
    cmd+=['vopt -O5 work.tb_bag_profiles -o bag_opt','vsim -t 1ps work.bag_opt','run -all','quit -code 0 -force']
    (run/'run.do').write_text('\n'.join(cmd)+'\n');env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'))
    proof=dict(result='RUNNING',started_utc=datetime.now(timezone.utc).isoformat(),inputs={str(x.relative_to(ROOT)):sha(x) for x in inputs},clock_ns=8,expected_sha256=sha(run/'expected.mem'))
    path=run/'summary.json';path.write_text(json.dumps(proof,indent=2)+'\n');print(f'BAG_PROFILES_RUN {run}',flush=True)
    with (run/'console.log').open('wb') as log:
        code=subprocess.run([str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do'],cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1200).returncode
    text=(run/'transcript.log').read_text(errors='replace');passed=code==0 and 'BAG_PROFILES_PASS' in text and '** Error' not in text and '** Fatal' not in text;error=None
    if passed:
        try:
            assert bytes.fromhex(''.join((run/'wire.mem').read_text().split()))==expected
            rows=list(csv.DictReader((run/'events.csv').open()));assert len(rows)==16
            for n in range(8):
                first,second=rows[n*2:n*2+2];gap=int(second['start'])-int(first['start']);bag=125000<<n
                assert int(first['bag'])==int(second['bag'])==bag and bag<=gap<=bag+128
            assert all(sha(ROOT/n)==h for n,h in proof['inputs'].items())
        except Exception as e:passed=False;error=repr(e)
    proof.update(result='PASS' if passed else 'FAIL',error=error,exit_code=code,
                 BAG_ms=[1,2,4,8,16,32,64,128],invalid_BAG_ms=[0,3],real_timers=True,
                 completed_utc=datetime.now(timezone.utc).isoformat())
    path.write_text(json.dumps(proof,indent=2)+'\n');print(text[-1200:]);print(json.dumps({k:v for k,v in proof.items() if k!='inputs'},indent=2))
    return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
