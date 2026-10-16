"""Run the transport RTL fault suite; real RAM/VO uses run_tftp_endpoint.py."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import csv
import json
import os
import shutil
import subprocess
from run_stage2_mgmt import ROOT,MS,sha
from generate_tftp_golden import generate


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    prefix='tftp';index=1
    while (ROOT/f'build/logs/{prefix}_{index:03d}').exists():index+=1
    run=ROOT/f'build/logs/{prefix}_{index:03d}';run.mkdir(parents=True)
    sources=[ROOT/'rtl/afdx_tftp_engine.v',ROOT/'sim/tb_tftp.sv']
    inputs=sources+[Path(__file__),ROOT/'scripts/generate_tftp_golden.py',ROOT/'scripts/run_stage2_mgmt.py']
    for p in inputs:shutil.copy2(p,run/p.name)
    golden=generate(run/'golden')
    shutil.copy2(MS.parent/'modelsim.ini',run/'modelsim.ini');os.chmod(run/'modelsim.ini',0o666)
    commands=['onerror {quit -code 2 -force}','vlib work','vmap work work']
    commands += [f'vlog {"-sv " if p.suffix==".sv" else ""}{p.name}' for p in sources]
    commands += ['vopt -O5 work.tb_tftp -o tftp_opt','vsim -t 1ps work.tftp_opt','run -all','quit -code 0 -force']
    (run/'run.do').write_text('\n'.join(commands)+'\n')
    env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'))
    summary=dict(result='RUNNING',started_utc=datetime.now(timezone.utc).isoformat(),scope='bounded RFC1350 octet client/server module, not 615A acceptance',
                 inputs={str(p):sha(p) for p in inputs},RTL_DUT_compiled=True,force_used=False,
                 golden={p.name:sha(p) for p in (run/'golden').iterdir()})
    proof=run/'summary.json';proof.write_text(json.dumps(summary,indent=2)+'\n')
    with (run/'console.log').open('wb') as log:
        code=subprocess.run([str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do'],
                            cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=900).returncode
    text=(run/'transcript.log').read_text(errors='replace');error=None;evidence={}
    passed=code==0 and 'TFTP_DIRECTED_PASS' in text and '** Error' not in text and '** Fatal' not in text
    if passed:
        try:
            actual=bytes.fromhex(''.join((run/'actual.mem').read_text().split()))
            assert actual==bytes.fromhex(''.join(p['data'] for p in golden['packets'])), 'independent TFTP bytes'
            events=list(csv.DictReader((run/'packets.csv').open()))
            assert len(events)==len(golden['packets'])
            for i,(event,packet) in enumerate(zip(events,golden['packets'])):
                assert int(event['bytes'])==len(bytes.fromhex(packet['data']))
                assert int(event['dst_port'])==packet['dst']
                if 'retry_wait_cycles' in packet:
                    gap=int(event['start_cycle'])-int(events[i-1]['cycle'])
                    assert packet['retry_wait_cycles']<=gap<=packet['retry_wait_cycles']+6, f'retry backoff {gap}'
            commits=list(csv.DictReader((run/'commits.csv').open()))
            assert [c['data'] for c in commits]==golden['commits'],'atomic images'
            for commit in commits:assert int(commit['length'])==len(bytes.fromhex(commit['data']))
            evidence=dict(scenarios=len(golden['cases']),packets=len(events),bytes=len(actual),atomic_commits=len(commits),
                          tx_backpressure=True,file_write_backpressure=True,client_server=True,exponential_backoff=True,clock_ns=8,full_system_VO='NOT RUN')
        except (AssertionError,KeyError,ValueError) as exc:passed=False;error=str(exc)
    summary.update(result='PASS' if passed else 'FAIL',exit_code=code,error=error,evidence=evidence,completed_utc=datetime.now(timezone.utc).isoformat(),
                   artifacts={p.name:sha(p) for p in run.iterdir() if p.is_file() and p.name!='summary.json'})
    proof.write_text(json.dumps(summary,indent=2)+'\n');print(text[-1800:]);print(json.dumps(dict(run=str(run),result=summary['result'],evidence=evidence,error=error),indent=2))
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
