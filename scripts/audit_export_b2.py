"""Audit the successful GUI database and export functional VO on a copy only."""
from pathlib import Path
import hashlib,json,re,shutil,subprocess
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT/'runs/elinx_002/AFDXB2'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    mpath=PROJECT.parent/'project_manifest.json';m=json.loads(mpath.read_text())
    synth=PROJECT/'AFDXB2.runs/synth_1'
    rpt=synth/'AFDXB2.map.rpt';text=rpt.read_text(errors='replace')
    rows=[]
    for line,raw in enumerate(text.splitlines(),1):
        match=re.search(r'Warning \((\d+)\): (.*)',raw)
        if not match:continue
        code=int(match[1]);category={10858:'undriven_wrapper_diagnostic',10030:'undriven_wrapper_diagnostic',10270:'frozen_MAC_case_default',10230:'frozen_MAC_width_truncation',10036:'unused_parser_register',276020:'RAM_read_during_write_bypass',13024:'constant_output_group',13410:'constant_profile_output'}[code]
        rows.append({'index':len(rows)+1,'report_line':line,'code':code,'category':category,'message':match[2]})
    assert len(rows)==34
    for row in m['sources']:
        assert sha(Path(row['original']))==row['sha256'],row
        assert sha(Path(row['snapshot']))==row['snapshot_sha256'],row
    util=(synth/'AFDXB2_utilization_synth.rpt').read_text()
    assert 'Synthesis Status : Successful' in util
    assert 'afdx_b2_synth_wrap' in util
    assert 'device_name="EQ6HL45"' in (synth/'AFDXB2_cluster.xml').read_text(errors='replace')
    assert 'set packageName "CSG225"' in (synth/'AFDXB2_pack.tcl').read_text()
    edc=Path(m['clock_constraint']);assert '-period 8.000' in edc.read_text()
    assert 'clock_125mhz.edc' in (PROJECT/'AFDXB2.epr').read_text()
    for entity in ('afdx_single_vl_tx:sender','afdx_bag_gate:bag_gate','mac_gmii_core:mac','afdx_single_vl_rx_candidate:rx_protocol','afdx_single_vl_sn_gate:sn_gate'):
        assert entity in text,entity
    assert '72688' in text and '23536' in text and '49152' in text
    assert 'state.PASS' in text and 'state.DRAIN' in text
    index=1
    while (ROOT/f'runs/eda_export_{index:03d}').exists():index+=1
    run=ROOT/f'runs/eda_export_{index:03d}';run.mkdir()
    work=run/'export_work/AFDXB2';work.parent.mkdir()
    shutil.copytree(PROJECT,work)
    # EDA settings point only to the archived copy; no synthesis or fitting.
    qsf=work/'AFDXB2.qsf'
    qsf.write_text(qsf.read_text().replace(PROJECT.as_posix(),work.as_posix()))
    audit={'result':'PASS_WITH_DIAGNOSTIC_LIMITATION','timestamp_utc':datetime.now(timezone.utc).isoformat(),
      'gui_project':str(PROJECT),'warning_count':34,'warnings':rows,
      'resources':{'LUT':3471,'FF':1422,'IO':138,'IO_available_GUI':160,'Memory_blocks':20,'RAM_logical_bits':72688},
      'RAMs':[{'depth':2048,'width':8,'count':3},{'depth':1471,'width':8,'count':2}],
      'clock_constraint':{'path':str(edc),'sha256':sha(edc),'text':edc.read_text(),'selected_in_EPR':True,'timing_closure':'NOT VERIFIED'},
      'diagnostic_addr_1':'UNDRIVEN: not usable as TX rejection counter; excluded from acceptance claims',
      'combinational_loop_logic_cells':33,'combinational_loop_note':'Synthesis statistics; investigate mapping structure in functional VO, not a timing PASS',
      'frozen_source_hashes_verified':True,'synthesis_repeated':False,'implementation_executed':False,
      'POST_SYNTH_TIMING':'NOT VERIFIED','EQ6_NATIVE_NETLIST_EQUIVALENCE':'NOT VERIFIED','DIAGNOSTIC_IO_FIT':'INCOMPATIBLE',
      'physical_package_fit':'NOT VERIFIED',
      'synthesis_artifacts':[{'path':str(p),'sha256':sha(p)} for p in synth.iterdir() if p.is_file()]}
    (run/'synthesis_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    eda=Path(r'D:\FPGA\eLinx3.0\bin\Passkey\bin\quartus_eda.exe')
    command=[str(eda),'--read_settings_files=on','--write_settings_files=off','--simulation=on','--functional=on','--tool=modelsim','--format=verilog','AFDXB2']
    started=datetime.now(timezone.utc).isoformat()
    result=subprocess.run(command,cwd=work,capture_output=True,timeout=300)
    log=result.stdout+result.stderr;(run/'export.log').write_bytes(log)
    vo=work/'simulation/modelsim/AFDXB2.vo'
    passed=result.returncode==0 and vo.is_file() and '0 errors' in log.decode(errors='replace').lower()
    if passed:
        assert re.search(r'\bmodule\s+afdx_b2_synth_wrap\b',vo.read_text(errors='replace'))
        delivered=run/'afdx_b2_synth_wrap.vo';shutil.copy2(vo,delivered)
    provenance={'result':'PASS' if passed else 'FAIL','started_utc':started,'completed_utc':datetime.now(timezone.utc).isoformat(),'command':command,'exit_code':result.returncode,'gui_project':str(PROJECT),'copy_work':str(work),'gui_manifest_sha256':sha(mpath),'eda_sha256':sha(eda),'synthesis_audit_sha256':sha(run/'synthesis_audit.json'),'export_log_sha256':sha(run/'export.log'),'synthesis_or_fit_executed':False,'backend_device':'EP1S80F1508C6 / Stratix compatibility functional model','EQ6_NATIVE_NETLIST_EQUIVALENCE':'NOT VERIFIED'}
    if passed:provenance.update(delivered_netlist=str(delivered),delivered_netlist_sha256=sha(delivered))
    (run/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print(log.decode(errors='replace')[-2500:]);print('B2_FUNCTIONAL_EXPORT',provenance['result'],run)
    return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
