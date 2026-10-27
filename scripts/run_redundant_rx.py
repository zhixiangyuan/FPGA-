"""All 4096 receive VL states, independent Python integrity/dedup oracle."""
from pathlib import Path
from datetime import datetime, timezone
import csv, json, os, shutil, subprocess
from run_competition import ROOT, MS, sha
from modelsim_support import prepare_ini

def generate(run):
    cases, expected = [], []
    psn, last, epochs, active_epoch, expired = {}, {}, {}, {}, set()
    def add(channel, vl, sn, delay=0):
        if delay>=625000:expired.update(last)
        key = (channel, vl); previous = psn.get(key)
        legal = 0x1234 <= vl < 0x2234
        seq_next = lambda n: n % 255+1
        integrity = vl==0x2233 or previous is None or sn == seq_next(previous) or sn == seq_next(seq_next(previous))
        delivered = False
        if legal:
            psn[key] = sn
            if sn:
                distance = (sn-last[vl]) % 255 if vl in last else None
                delivered = integrity and (vl==0x2231 or vl in expired or
                    (epochs.get(key,0)==active_epoch.get(vl,0) and (distance is None or 1 <= distance <= 127)))
                if delivered:
                    last[vl] = sn;active_epoch[vl]=epochs.get(key,0);expired.discard(vl)
            else:
                epoch=epochs.get(key,0) if previous==0 else (epochs.get(key,0)+1)%256
                epochs[key]=epoch
                distance=(epoch-active_epoch.get(vl,0))%256
                if 1<=distance<=127:
                    active_epoch[vl]=epoch;last.pop(vl,None)
        cases.append((channel, vl, sn, int(delivered)|(delay<<1)))
        if delivered:
            expected.append(vl.to_bytes(2, 'big')+len(cases).to_bytes(3, 'big'))
    # Every RAM address, independent per-network state, duplicate suppression.
    for offset in range(4096):
        vl = 0x1234+offset
        add(offset % 2, vl, 1); add(1-offset % 2, vl, 1)
        add(offset % 2, vl, 2); add(1-offset % 2, vl, 2)
    # Delayed old B copy, skipped frame, invalid jump and recovery, SN zero.
    v = 0x1234
    for c, s in ((0,3),(0,4),(1,3),(1,4),(0,6),(1,6),(0,100),(0,101),
                 (1,7),(1,8),(0,0),(1,0),(0,254),(1,254),(0,255),(1,255),(0,1),(1,1)):
        add(c,v,s)
    # Full wrap with the other channel taking alternate lead.
    for n in range(2,258):
        s = (n-1) % 255+1
        add(n%2,v,s);add(1-n%2,v,s)
    add(0,0x1233,1);add(1,0x2234,1)
    for c,s in ((0,100),(1,100),(0,200),(1,200)):add(c,0x2233,s)
    # Reset-generation counter wrap: both networks agree through 256 resets.
    for _ in range(256):
        for c,s in ((0,0),(1,0),(0,1),(1,1)):add(c,0x1234,s)
    # Late SN0 on B must not reset the already delivered new-generation A1.
    v=0x2232
    for c,s in ((0,0),(0,1),(1,0),(1,1),(0,2),(1,2)):
        add(c,v,s)
    # Real 5ms SkewMAX expiry; IC still has to accept B3 (previous B2).
    add(0,v,3);add(1,v,3,delay=625001)
    # Even after SkewMAX, an IC-invalid jump is discarded, then +1 recovers.
    add(0,v,200,delay=625001);add(0,v,201)
    (run/'vectors.mem').write_text(f'{len(cases):032x}\n'+''.join(''.join(f'{x:08x}' for x in row)+'\n' for row in cases))
    (run/'expected.json').write_text(json.dumps([p.hex() for p in expected]))
    return cases, expected

def main():
    i=1
    while (ROOT/f'build/logs/redundant_rx_{i:03d}').exists(): i+=1
    run=ROOT/f'build/logs/redundant_rx_{i:03d}';run.mkdir(parents=True)
    files=[ROOT/'rtl/afdx_redundant_rx.v',ROOT/'sim/tb_redundant_rx.sv']
    inputs=files+[Path(__file__),ROOT/'scripts/run_competition.py',ROOT/'scripts/modelsim_support.py']
    for p in inputs:shutil.copy2(p,run/p.name)
    cases,expected=generate(run);prepare_ini(run,MS)
    commands=['onerror {quit -code 2 -force}','vlib work','vlog afdx_redundant_rx.v',
              'vlog -sv tb_redundant_rx.sv','vopt -O5 work.tb_redundant_rx -o rx_opt',
              'vsim -t 1ps work.rx_opt','run -all','quit -code 0 -force']
    (run/'run.do').write_text('\n'.join(commands)+'\n')
    proof=dict(result='RUNNING',started_utc=datetime.now(timezone.utc).isoformat(),
               inputs={str(p.relative_to(ROOT)):sha(p) for p in inputs},
               vectors_sha256=sha(run/'vectors.mem'),expected_sha256=sha(run/'expected.json'))
    (run/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'))
    print(f'REDUNDANT_RX_RUN {run}',flush=True)
    with (run/'console.log').open('wb') as log:
        code=subprocess.run([str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log',
                             '-do','do run.do'],cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600).returncode
    text=(run/'transcript.log').read_text(errors='replace')
    passed=code==0 and 'REDUNDANT_RX_PASS' in text and '** Error' not in text and '** Fatal' not in text
    error=None
    if passed:
        try:
            actual=[];packet=bytearray()
            for r in csv.DictReader((run/'rx_unit.csv').open()):
                if int(r['sop']):assert not packet
                packet.append(int(r['data']))
                if int(r['eop']):actual.append(bytes(packet));packet.clear()
            assert not packet and actual==expected, f'oracle mismatch actual={len(actual)} expected={len(expected)}'
            assert all(sha(ROOT/n)==h for n,h in proof['inputs'].items())
        except Exception as exc:passed=False;error=repr(exc)
    proof.update(result='PASS' if passed else 'FAIL',exit_code=code,error=error,
                 vectors=len(cases),application_deliveries=len(expected),VLs_exercised=4096,
                 independent_AB_integrity=True,duplicate_late_old_copy=True,wraparound=True,
                 reset_control=True,late_SN0_generation=True,reset_generation_wrap_256=True,
                 per_VL_integrity_and_redundancy_disable=True,clock_ns=8,
                 recovery_timeout_test='real 625001-cycle waits; expiry never bypasses IC',synthesis='NOT RUN',
                 completed_utc=datetime.now(timezone.utc).isoformat())
    (run/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(text[-1400:]);print(json.dumps({k:v for k,v in proof.items() if k!='inputs'},indent=2))
    return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
