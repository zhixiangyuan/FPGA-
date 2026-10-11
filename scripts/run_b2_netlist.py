"""One real VO run, full approved Golden, live durable logs and provenance."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys,time
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
MS=Path(r'D:\FPGA\Modlesim20.4\ModelSim20.4\win64')
LIB=Path(r'D:\FPGA\eLinx3.0\Simulation\elinx_lib')
EXPORT=ROOT/'runs/eda_export_001'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
def write(p,data):
    temp=p.with_suffix(p.suffix+'.tmp');temp.write_text(json.dumps(data,indent=2)+'\n');temp.replace(p)
def main():
    lock=ROOT/'runs/B2_NETLIST_RUNNING.lock'
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    index=1
    while (ROOT/f'runs/netlist_{index:03d}').exists():index+=1
    run=ROOT/f'runs/netlist_{index:03d}';run.mkdir()
    os.write(fd,json.dumps({'runner_pid':os.getpid(),'run':str(run),'started_utc':now()}).encode());os.close(fd)
    started=now();summary={'result':'PREPARING','run':str(run),'suite':'real_functional_VO_full_SN_protocol','started_utc':started,'runner_pid':os.getpid()}
    write(run/'summary.json',summary)
    try:
        exp=json.loads((EXPORT/'provenance.json').read_text())
        assert exp['result']=='PASS'
        vo=Path(exp['delivered_netlist']);assert sha(vo)==exp['delivered_netlist_sha256']
        compile_sources=[LIB/'altera_primitives.v',LIB/'220model.v',LIB/'stratix_atoms.v',vo,ROOT/'sim/tb_b2_netlist_protocol.sv']
        inputs=compile_sources+[ROOT/'scripts/generate_b2_full_golden.py',ROOT/'scripts/generate_b2_golden.py',ROOT/'scripts/verify_b2_full.py',Path(__file__)]
        for src in inputs:shutil.copy2(src,run/src.name)
        summary['sources']=[{'path':str(p),'sha256':sha(p),'snapshot_sha256':sha(run/p.name)} for p in inputs]
        with (run/'golden_generation.log').open('wb') as log:
            golden=subprocess.run([sys.executable,str(ROOT/'scripts/generate_b2_full_golden.py'),'--out',str(run/'golden')],stdout=log,stderr=subprocess.STDOUT,timeout=60)
        assert golden.returncode==0
        summary['golden_sha256']=sha(run/'golden/sha256.json')
        shutil.copy2(MS.parent/'modelsim.ini',run/'modelsim.ini');os.chmod(run/'modelsim.ini',0o666)
        top='tb_b2_netlist_protocol'
        do=['onerror {quit -code 2 -force}','vlib work','vmap work work']
        do += [f'vlog {"-sv" if p.suffix==".sv" else ""} +incdir+{{{run.as_posix()}}} {{{(run/p.name).as_posix()}}}' for p in compile_sources]
        do += [f'vopt -O5 -inlineFactor=100 +acc=nr+{top} work.{top} -o b2_netlist_optimized',
               'vsim -t 1ps -onfinish stop -wlf waves.wlf work.b2_netlist_optimized']
        observed=('reset','psn','psn_valid','gmii_txd','gmii_tx_en','gmii_rxd','gmii_rx_dv','inject','app_data','app_valid','app_ready','app_sop','app_eop','app_sn','candidate_banks_busy','diag_addr','diag_data','msg_done','late_count')
        do+=['log '+' '.join(f'/{top}/{x}' for x in observed),'run -all','quit -code 0 -force']
        (run/'run.do').write_text('\n'.join(do)+'\n')
        env=os.environ.copy();env['MGLS_LICENSE_FILE']=str(MS.parent/'LICENSE.TXT')
        command=[str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do']
        provenance={'started_utc':started,'command':command,'actual_DUT':'afdx_b2_synth_wrap.vo','RTL_DUT_compiled':False,'force_used':False,'compile_sources':[str(run/p.name) for p in compile_sources],
          'export_provenance':str(EXPORT/'provenance.json'),'export_provenance_sha256':sha(EXPORT/'provenance.json'),
          'sources':summary['sources'],'golden_sha256':summary['golden_sha256'],'clock_ns':8,'BAG_cycles':125000,'SN_wrap_frames':256,
          'diagnostic_addr_1':'UNSUPPORTED: not asserted','WLF_scope':'top pins and sampled diagnostic bus; clock not logged',
          'POST_SYNTH_TIMING':'NOT VERIFIED','EQ6_NATIVE_NETLIST_EQUIVALENCE':'NOT VERIFIED'}
        write(run/'provenance.json',provenance)
        with (run/'console.log').open('wb') as log:
            p=subprocess.Popen(command,cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT)
            summary.update(result='RUNNING',modelsim_pid=p.pid,command=command);write(run/'summary.json',summary)
            print('B2_NETLIST_RUN',run,'PID',p.pid,flush=True)
            try:code=p.wait(timeout=86400)
            except subprocess.TimeoutExpired:
                summary.update(result='TIMEOUT',completed_utc=now());write(run/'summary.json',summary)
                subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True)
                raise
        text=(run/'transcript.log').read_text(errors='replace')
        passed=code==0 and all(marker in text for marker in ('B2_FULL_SN_PROTOCOL = PASS','B2_SN_CAPACITY_RESET = PASS','B2_REAL_VO_NETLIST = PASS','Errors: 0')) and '** Fatal' not in text and '** Error' not in text
        summary.update(result='PASS' if passed else 'FAIL',exit_code=code,completed_utc=now());write(run/'summary.json',summary)
        if passed:
            with (run/'verification.log').open('wb') as log:
                verify=subprocess.run([sys.executable,str(run/'verify_b2_full.py'),str(run)],stdout=log,stderr=subprocess.STDOUT)
            if verify.returncode:summary['result']='FAIL_INDEPENDENT_VERIFICATION';write(run/'summary.json',summary);passed=False
        summary['artifact_hashes']={p.name:sha(p) for p in run.iterdir() if p.is_file() and p.name not in ('summary.json',)}
        write(run/'summary.json',summary)
        print(text[-2200:]);print('B2_REAL_NETLIST',summary['result'],run,flush=True)
        return 0 if passed else 1
    except Exception as exc:
        summary.update(result=summary['result'] if summary['result']=='TIMEOUT' else 'FAIL',error=repr(exc),completed_utc=now());write(run/'summary.json',summary)
        raise
    finally:
        if lock.exists():lock.replace(run/'runner_closed.lock')
if __name__=='__main__':raise SystemExit(main())
