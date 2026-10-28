"""Same timestamps, bytes, faults, real clock and BAG; baseline or current RTL."""
from pathlib import Path
from datetime import datetime,timezone
from collections import defaultdict,deque
import argparse,csv,json,os,shutil,subprocess
from run_competition import ROOT,MS,sources,sha,verify
from frozen_frame_reference import payload
from modelsim_support import prepare_ini

def metrics(run):
    offers=list(csv.DictReader((run/'inputs.csv').open()))[:688];lookup=defaultdict(deque);offered={}
    for r in offers:
        cid,vl,n=(int(r[k]) for k in ('id','vl','length'));lookup[(vl,payload(cid,n))].append(cid);offered[cid]=r
    data=bytearray();observed=[]
    for r in csv.DictReader((run/'application.csv').open()):
        if int(r['sop']):assert not data;start=int(r['cycle'])
        data.append(int(r['data']))
        if int(r['eop']):
            vl=int.from_bytes(data[:2],'big');cid=lookup[(vl,bytes(data[2:]))].popleft();o=offered[cid]
            observed.append(dict(id=cid,vl=vl,length=int(o['length']),mode=int(r['mode']),
                first_ns=(start-int(o['cycle']))*8,last_ns=(int(r['cycle'])-int(o['cycle']))*8))
            data.clear()
    assert not data and len(observed)==688 and all(not v for v in lookup.values())
    def ranges(items):
        groups=defaultdict(list)
        for r in items:groups[(r['vl'],r['length'])].append(r)
        result=[]
        for (vl,n),v in groups.items():
            if len(v)>1:
                lo=min(v,key=lambda x:x['first_ns']);hi=max(v,key=lambda x:x['first_ns'])
                result.append(dict(vl=vl,length=n,samples=len(v),range_ns=hi['first_ns']-lo['first_ns'],minimum=lo,maximum=hi))
        return sorted(result,key=lambda x:x['range_ns'],reverse=True)
    all_ranges=ranges(observed)
    return dict(application_messages=688,max_first_to_first_ns=max(x['first_ns'] for x in observed),
        max_first_to_last_ns=max(x['last_ns'] for x in observed),max_all_scenarios_jitter_ns=all_ranges[0]['range_ns'],
        all_scenarios_ranges=all_ranges,by_mode={str(m):ranges([x for x in observed if x['mode']==m]) for m in range(4)},
        steady_ranges=ranges([x for x in observed if x['id']>=176]),target_10us_met=all_ranges[0]['range_ns']<=10000)

def main():
    p=argparse.ArgumentParser();p.add_argument('--ref');p.add_argument('--timeout',type=int,default=2400)
    p.add_argument('--bias',type=int,choices=range(0,65));a=p.parse_args()
    i=1
    while True:
        run=ROOT/f'build/logs/jitter_replay_{i:03d}'
        try:run.mkdir(parents=True);break
        except FileExistsError:i+=1
    golden=run/'golden';golden.mkdir()
    reference=ROOT/'build/logs/competition_010';refproof=json.loads((reference/'summary.json').read_text())
    assert refproof['result']=='PASS'
    offers=list(csv.DictReader((reference/'inputs.csv').open()));assert len(offers)==691
    (golden/'offers.mem').write_text(''.join(f'{int(r["cycle"]):08x}{int(r["vl"]):04x}{int(r["length"]):04x}{int(r["id"]):08x}\n' for r in offers))
    modes=[(int(offers[n]['cycle'])-125001,m) for n,m in ((128,1),(144,2),(160,3),(176,0))]
    (golden/'modes.mem').write_text(''.join(f'{c:08x}{m:02x}\n' for c,m in modes))
    (golden/'constants.vh').write_text(f'localparam OFFER_COUNT={len(offers)};\n')
    if a.ref:
        old=json.loads(subprocess.check_output(['git','show',f'{a.ref}:reports/REQUIREMENTS_COVERAGE_20261027.json'],cwd=ROOT))
        names=[Path(n.replace('\\','/')) for n in old['canonical_sources']]
    else:names=[x.relative_to(ROOT) for x in sources()]
    inputs={}
    for name in names:
        target=run/name.name
        if a.ref:target.write_bytes(subprocess.check_output(['git','show',f'{a.ref}:{name.as_posix()}'],cwd=ROOT))
        else:shutil.copy2(ROOT/name,target)
        inputs[name.as_posix()]=sha(target)
    tb=ROOT/'sim/tb_jitter_replay.sv';shutil.copy2(tb,run/tb.name)
    helpers=[Path(__file__),ROOT/'scripts/run_competition.py',ROOT/'scripts/frozen_frame_reference.py',ROOT/'scripts/generate_stage2_mgmt_golden.py',ROOT/'scripts/modelsim_support.py']
    for h in helpers:shutil.copy2(h,run/h.name)
    prepare_ini(run,MS)
    commands=['onerror {quit -code 2 -force}','vlib work']+[f'vlog {n.name}' for n in names]
    define=f'+define+JITTER_BIAS_16={a.bias} ' if a.bias is not None else ''
    commands+=[f'vlog -sv {define}tb_jitter_replay.sv','vopt -O5 work.tb_jitter_replay -o jitter_opt','vsim -t 1ps work.jitter_opt','run -all','quit -code 0 -force']
    (run/'run.do').write_text('\n'.join(commands)+'\n')
    proof=dict(result='RUNNING',started_utc=datetime.now(timezone.utc).isoformat(),source_ref=a.ref or 'working tree',
        production_sources=inputs,Testbench_sha256=sha(tb),helpers={str(h.relative_to(ROOT)):sha(h) for h in helpers},
        golden={f.name:sha(f) for f in golden.iterdir()},clock_ns=8,BAG_cycles=125000,
        fixed_offered_source_sha256=sha(reference/'inputs.csv'),reference_summary_sha256=sha(reference/'summary.json'),
        parameter_overrides=dict(LENGTH_BIAS_16=a.bias) if a.bias is not None else {})
    path=run/'summary.json';path.write_text(json.dumps(proof,indent=2)+'\n')
    env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'))
    print(f'JITTER_REPLAY_RUN {run}',flush=True)
    with (run/'console.log').open('wb') as log:
        proc=subprocess.Popen([str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do'],cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT)
        proof['pid']=proc.pid;path.write_text(json.dumps(proof,indent=2)+'\n')
        try:code=proc.wait(timeout=a.timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=log,stderr=subprocess.STDOUT);code=proc.wait()
    log=(run/'transcript.log').read_text(errors='replace');ok=code==0 and 'JITTER_REPLAY_FUNCTIONAL_PASS' in log and '** Error' not in log and '** Fatal' not in log
    error=None;result={}
    if ok:
        try:
            assert (run/'inputs.csv').read_bytes()==(reference/'inputs.csv').read_bytes(),'offered timestamps changed'
            result=metrics(run);result['steady_original_assertions']=verify(run)
            assert all(sha(run/Path(n).name)==h for n,h in inputs.items())
            assert all(sha(golden/n)==h for n,h in proof['golden'].items())
            assert sha(tb)==proof['Testbench_sha256'] and all(sha(ROOT/n)==h for n,h in proof['helpers'].items())
        except Exception as exc:ok=False;error=repr(exc)
    proof.update(result=('PASS_10US' if result.get('target_10us_met') else 'FUNCTIONAL_PASS_TARGET_NOT_MET') if ok else 'FAIL',
        exit_code=code,error=error,evidence=result,completed_utc=datetime.now(timezone.utc).isoformat())
    path.write_text(json.dumps(proof,indent=2)+'\n')
    print(log[-700:]);print(json.dumps({k:v for k,v in proof.items() if k not in ('production_sources','helpers','golden','evidence')},indent=2))
    if result:print(json.dumps({k:result[k] for k in ('max_first_to_first_ns','max_all_scenarios_jitter_ns','target_10us_met')},indent=2))
    return 0 if ok else 1

if __name__=='__main__':raise SystemExit(main())
