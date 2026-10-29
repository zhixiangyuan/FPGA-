"""Implementation self-test: automated stimulus, explicitly not user-recorded video."""
import copy,json,time
from interactive_demo import Session,run_batch,verify,dump,ROOT,sha,compare_provenance,compare_actual_inputs,self_test

def wait_file(session,name,timeout=240):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        p=session.run/name
        if p.exists():return p
        if session.process.poll() is not None:raise RuntimeError(f'ModelSim exited: {session.run}')
        time.sleep(.2)
    raise TimeoutError(f'{session.run}/{name}')

def gui_action(s,fn):
    duration=fn();(s.run/'request.txt').write_text(str(duration))
    response=wait_file(s,'response.txt');assert response.read_text().strip()=='DONE';response.unlink()
    proof=s.result();assert proof['result']=='PASS',proof
    return proof

def main():
    self_test();results=[]
    # Successive commands run in a genuine GUI simulation, each stops before next.
    s=Session(3);wait_file(s,'ready.txt')
    try:
        results.append(gui_action(s,lambda:s.app(0x1234,'界面链路'.encode(),interval=64)))
        for mask,error in ((1,0),(2,0),(3,1),(3,0)):
            results.append(gui_action(s,lambda:s.fault(mask,error)))
            results.append(gui_action(s,lambda:s.app(0x1234,f'net-{mask}-{error}'.encode(),interval=64)))
        for value in (None,b'GUI-user-set',None):results.append(gui_action(s,lambda:s.snmp(4,value)))
        results.append(gui_action(s,lambda:s.sync(250)))
        for sn in (255,1,3,20,21,21,0,1):results.append(gui_action(s,lambda:s.inject(0x12a0,b'SN-policy',sn,'正常报文')))
        for bad in ('FCS错误','IP校验错误','UDP长度错误'):results.append(gui_action(s,lambda:s.inject(0x12a1,b'bad-recovery',1,bad)))
        results.append(gui_action(s,lambda:s.inject(0x12a1,b'bad-recovery',1,'正常报文')))
        plan=copy.deepcopy(s.plan);plan['wire'].pop()
        try:verify(s.run,plan)
        except AssertionError:negative='PASS: wrong Golden is rejected'
        else:raise AssertionError('Oracle accepted missing expected wire')
        try:s.app(0x1234,b'',interval=64)
        except AssertionError:empty='PASS: empty user data rejected before command'
        else:raise AssertionError('Empty user data accepted')
    finally:(s.run/'close.txt').write_text('self-test complete')
    # New independent input equality and arbiter-only source comparison.
    baseline=ROOT/'build/logs/service_pressure_010/afdx_service_tx_arbiter_615a.v'
    hist=json.loads((baseline.parent/'summary.json').read_text())
    assert hist['result']=='PASS'
    assert [v for p,v in hist['inputs'].items() if p.endswith(baseline.name)]==[sha(baseline)]
    reference=ROOT/'build/logs/service_pressure_011'
    left=Session(8,batch=True,arbiter=baseline,reference=reference);right=Session(8,batch=True,reference=reference)
    ld=left.pressure(24);rd=right.pressure(24);provenance=compare_provenance(left,right)
    lp=run_batch(left,[ld]);rp=run_batch(right,[rd])
    provenance=compare_actual_inputs(left,right,provenance)
    compare=dict(result='PASS',provenance=provenance,before=lp,after=rp)
    dump(right.run/'comparison.json',compare)
    report=dict(result='PASS',kind='automated implementation validation; not human GUI acceptance or official full regression',
                GUI_transport_results=results,wrong_Golden_test=negative,empty_input_test=empty,comparison=compare)
    dump(ROOT/'reports/交互演示实现验证.json',report)
    print(json.dumps(dict(result='PASS',GUI_run=str(s.run),comparison=str(right.run/'comparison.json')),ensure_ascii=False))

if __name__=='__main__':main()
