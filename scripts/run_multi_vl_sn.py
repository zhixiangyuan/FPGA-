"""ModelSim RTL unit regression with independently generated SN decisions."""
from pathlib import Path
import csv,json,hashlib,os,shutil,subprocess
from datetime import datetime,timezone
from generate_multi_vl_sn_golden import generate

ROOT=Path(__file__).resolve().parents[1]
MS=Path(os.environ.get('MODELSIM_BIN',r'D:\FPGA\Modlesim20.4\ModelSim20.4\win64'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    parent=ROOT/'build/logs';parent.mkdir(parents=True,exist_ok=True)
    i=1
    while (parent/f'multi_vl_sn_{i:03d}').exists():i+=1
    run=parent/f'multi_vl_sn_{i:03d}';run.mkdir()
    inputs=[ROOT/'rtl/afdx_multi_vl_sn_gate.v',ROOT/'sim/tb_multi_vl_sn.sv',Path(__file__),ROOT/'scripts/generate_multi_vl_sn_golden.py']
    for p in inputs:shutil.copy2(p,run/p.name)
    manifest=generate(run/'golden')
    shutil.copy2(MS.parent/'modelsim.ini',run/'modelsim.ini');os.chmod(run/'modelsim.ini',0o666)
    lines=['onerror {quit -code 2 -force}','vlib work','vmap work work',
           'vlog afdx_multi_vl_sn_gate.v','vlog -sv tb_multi_vl_sn.sv',
           'vsim -t 1ps -wlf waves.wlf work.tb_multi_vl_sn','log -r /tb_multi_vl_sn/*','run -all','quit -code 0 -force']
    (run/'run.do').write_text('\n'.join(lines)+'\n')
    env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'))
    command=[str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do']
    summary={'result':'RUNNING','started_utc':datetime.now(timezone.utc).isoformat(),'command':command,
             'inputs':{str(p.relative_to(ROOT)):sha(p) for p in inputs},'golden':manifest}
    (run/'summary.json').write_text(json.dumps(summary,indent=2))
    with (run/'console.log').open('wb') as log:
        code=subprocess.run(command,cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300).returncode
    text=(run/'transcript.log').read_text(errors='replace')
    passed=code==0 and 'MULTI_VL_SN = PASS' in text and 'Errors: 0' in text and '** Fatal' not in text and '** Error' not in text
    independently_checked=0
    verification_error=None
    if passed:
        expected=[list(map(int,line.split())) for line in (run/'golden/vectors.txt').read_text().splitlines()]
        actual=list(csv.DictReader((run/'actual_sn.csv').open()))
        assert len(actual)==sum(r[0]==0 for r in expected)
        counts=[0,0,0,0];position=0
        for number,row in enumerate(expected):
            if row[0]==1:counts=[0,0,0,0];continue
            a=actual[position];position+=1
            _,vl,sn,length,decision,missing,en=row
            counts[decision-1]+=1;counts[3]+=missing
            assert [int(a[k]) for k in ('vector','vl','sn','decision')]==[number,vl,sn,decision]
            assert [int(a[k]) for k in ('accepted','rejected','control','missing','delivered')]==counts+[counts[0]]
            if int(a['psn'])!=(sn if 0<=vl<16 else -1):
                verification_error=f'PSN CSV mismatch at vector {number}'
                passed=False
                break
            independently_checked+=1
    summary.update(result='PASS' if passed else 'FAIL',exit_code=code,independent_decisions_checked=independently_checked,
                   verification_error=verification_error,
                   completed_utc=datetime.now(timezone.utc).isoformat(),
                   artifacts={p.name:sha(p) for p in run.iterdir() if p.is_file() and p.name!='summary.json'})
    (run/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(text[-1800:]);print(json.dumps({'run':str(run),'result':summary['result'],'independent_decisions_checked':independently_checked}))
    return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
