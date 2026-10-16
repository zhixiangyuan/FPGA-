"""Real atomic RAM plus transport acceptance; optional genuine module VO."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,csv,json,os,shutil,subprocess
from run_stage2_mgmt import ROOT,MS,sha
from generate_tftp_golden import generate_endpoint


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--vo',type=Path);parser.add_argument('--provenance',type=Path);args=parser.parse_args()
    if args.vo:
        assert args.provenance,'A real export provenance file is required'
        provenance=json.loads(args.provenance.read_text());assert provenance['result']=='PASS'
        assert sha(args.vo)==provenance['delivered_netlist_sha256']
        project=Path(provenance['source_project']);manifest=project/'project_manifest.json'
        assert sha(manifest)==provenance['source_manifest_sha256']
        for row in json.loads(manifest.read_text())['sources']:
            assert sha(ROOT/row['canonical_source'])==row['sha256']==sha(project/row['snapshot'])
    prefix='tftp_endpoint_vo' if args.vo else 'tftp_endpoint';index=1
    while (ROOT/f'build/logs/{prefix}_{index:03d}').exists():index+=1
    run=ROOT/f'build/logs/{prefix}_{index:03d}';run.mkdir(parents=True)
    sources=[ROOT/'rtl'/n for n in ('afdx_tftp_engine.v','afdx_atomic_file_store.v','afdx_tftp_file_endpoint.v')]
    if args.vo:sources=[ROOT/'build/logs/netlist_001'/n for n in ('altera_primitives.v','220model.v','stratix_atoms.v')]+[args.vo.resolve()]
    sources += [ROOT/'sim/tb_tftp_endpoint.sv']
    inputs=sources+[Path(__file__),ROOT/'scripts/generate_tftp_golden.py',ROOT/'scripts/run_stage2_mgmt.py']
    if args.vo:inputs+=[args.provenance]
    for p in inputs:shutil.copy2(p,run/p.name)
    golden=generate_endpoint(run/'golden')
    shutil.copy2(MS.parent/'modelsim.ini',run/'modelsim.ini');os.chmod(run/'modelsim.ini',0o666)
    commands=['onerror {quit -code 2 -force}','vlib work','vmap work work']+[f'vlog {"-sv " if p.suffix==".sv" else ""}{p.name}' for p in sources]
    commands += ['vopt -O5 work.tb_tftp_endpoint -o endpoint_opt','vsim -t 1ps work.endpoint_opt','run -all','quit -code 0 -force']
    (run/'run.do').write_text('\n'.join(commands)+'\n')
    env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'))
    summary=dict(result='RUNNING',started_utc=datetime.now(timezone.utc).isoformat(),scope='4KiB raw TFTP and atomic RAM; not 615A or whole-system acceptance',
                 RTL_DUT_compiled=not bool(args.vo),force_used=False,inputs={str(p):sha(p) for p in inputs},
                 golden={p.name:sha(p) for p in (run/'golden').iterdir()})
    proof=run/'summary.json';proof.write_text(json.dumps(summary,indent=2)+'\n')
    with (run/'console.log').open('wb') as log:
        proc=subprocess.Popen([str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do'],
            cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT)
        summary['modelsim_pid']=proc.pid;proof.write_text(json.dumps(summary,indent=2)+'\n');print(f'TFTP_ENDPOINT {run} PID {proc.pid}',flush=True)
        code=proc.wait(timeout=3600)
    text=(run/'transcript.log').read_text(errors='replace');error=None;evidence={}
    passed=code==0 and 'TFTP_ENDPOINT_PASS' in text and '** Error' not in text and '** Fatal' not in text
    if passed:
        try:
            actual=bytes.fromhex(''.join((run/'actual.mem').read_text().split()))
            assert actual==bytes.fromhex(''.join(p['data'] for p in golden['packets'])),'independent wire bytes'
            packets=list(csv.DictReader((run/'packets.csv').open()));metadata=list(csv.DictReader((run/'metadata.csv').open()))
            assert len(packets)==len(golden['packets']) and len(metadata)==len(golden['metadata'])
            for event,packet in zip(packets,golden['packets']):
                assert int(event['bytes'])==len(bytes.fromhex(packet['data'])) and int(event['dst_port'])==packet['dst']
            for event,expected in zip(metadata,golden['metadata']):
                assert {k:int(event[k],16 if k=='crc' else 10) for k in expected}==expected,'CRC/length/generation mismatch'
            evidence=dict(scenarios=len(golden['cases']),packets=len(packets),bytes=len(actual),metadata_checks=len(metadata),
                          atomic_RAM_readback=True,old_bank_preserved_on_error=True,CRC16_independent=True,clock_ns=8,
                          timeout_cycles=12500000,RTL_DUT_compiled=not bool(args.vo),whole_system_VO='NOT RUN')
        except (AssertionError,KeyError,ValueError) as exc:error=str(exc);passed=False
    summary.update(result='PASS' if passed else 'FAIL',exit_code=code,error=error,evidence=evidence,completed_utc=datetime.now(timezone.utc).isoformat(),
                   artifacts={p.name:sha(p) for p in run.iterdir() if p.is_file() and p.name!='summary.json'})
    proof.write_text(json.dumps(summary,indent=2)+'\n');print(text[-1300:]);print(json.dumps(dict(run=str(run),result=summary['result'],evidence=evidence,error=error),indent=2))
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
