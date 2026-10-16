"""Attempt the installed eLinx synthesized timing-report flow, without place/route."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import sqlite3
import subprocess

ROOT=Path(__file__).resolve().parents[1]
SHELL=Path(r'D:/FPGA/eLinx3.0/bin/shell/bin')


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def read_timing_database(path):
    """Read the SQLite timing-analysis database emitted by the installed tool."""
    db=sqlite3.connect(path)
    db.row_factory=sqlite3.Row
    try:
        clock=db.execute('select * from elinx_intra_clock_summary order by clock_summary_id limit 1').fetchone()
        timing=db.execute('select * from elinx_timing_summary limit 1').fetchone()
        if clock is None or timing is None:
            raise RuntimeError('native timing database has no clock/timing summary')
        path_row=db.execute('select * from elinx_intra_clock_longest_sync_path_report order by path_id limit 1').fetchone()
        unconstrained=[]
        for row in db.execute('select name,setup_worst_slack,setup_fail_ends,setup_total_ends,hold_worst_slack,hold_fail_ends,hold_total_ends from elinx_unconstrain_clock_summary'):
            unconstrained.append(dict(row))
        return {
            'clock': {
                'name':clock['name'],'period_ps':clock['period'],'fmax_mhz':clock['fmax'],
                'setup_wns_ps':clock['setup_worst_slack'],'setup_tns_ps':clock['setup_total_violation'],
                'setup_failing_endpoints':clock['setup_fail_ends'],'setup_endpoints':clock['setup_total_ends'],
                'hold_wns_ps':clock['hold_worst_slack'],'hold_tns_ps':clock['hold_total_violation'],
                'hold_failing_endpoints':clock['hold_fail_ends'],'hold_endpoints':clock['hold_total_ends'],
            },
            'design_summary':dict(timing),
            'critical_setup_path':None if path_row is None else {
                'from':path_row['from_cell_name'],'to':path_row['to_cell_name'],
                'slack_ps':path_row['slack'],'total_delay_ps':path_row['total_delay'],
                'logic_levels':path_row['levels'],'high_fanout':path_row['high_fanout'],
            },
            'unconstrained_path_groups':unconstrained,
        }
    finally:
        db.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-dir',type=Path,required=True)
    args=parser.parse_args();project=args.project_dir.resolve();family=project.name.split('_',1)[0]
    assert family in ('AFDXS2M','AFDXS2','AFDXSUB','AFDXTFTP')
    manifest=json.loads((project/'project_manifest.json').read_text())
    assert manifest['device']=='EQ6HL45' and manifest['package']=='CSG225'
    mapping=json.loads((project/'database_mapping_provenance.json').read_text())
    assert mapping['result']=='PASS'
    out=project/f'{family}.runs/synth_1'
    for row in manifest['sources']:
        assert sha(ROOT/row['canonical_source'])==sha(project/row['snapshot'])==row['sha256']
    graph=out/f'{family}.tbg.pb';version=out/f'{family}.ver.pb'
    for p in (graph,version):assert sha(p)==mapping['artifacts'][p.name]
    official=SHELL/'run_synthesized_timing_report.tcl'
    body=official.read_text(errors='replace')
    assert 'proc run_tming_report' in body
    assert not any(word in body for word in ('run_place ', 'run_route ', 'DoPlace', 'DoRoute', 'BitGenerator'))
    report=out/f'{family}.tan.rpt'
    database=out/f'{family}.tan.pb'
    audit=project/'native_timing';audit.mkdir(exist_ok=True)
    tcl=audit/'native_timing.tcl'
    wrapper=(f'cd {{{SHELL.as_posix()}}}\nsource {{{official.as_posix()}}}\n'
             f'run_tming_report {{{project.as_posix()}}} {family} {manifest["top"]} eHiChip6 EQ6HL45 synth_1\nexit 0\n')
    if tcl.exists() and tcl.read_text()!=wrapper:raise RuntimeError(f'Existing timing wrapper differs: {tcl}')
    if not tcl.exists():tcl.write_text(wrapper)
    tool=SHELL/'Implementation.exe';command=[str(tool),'-f',str(tcl)]
    logpath=audit/'console.log';old=audit/'provenance.json';reuse=False;error=None
    if database.exists():
        if not old.exists():raise FileExistsError(f'Preserve unproven timing database: {database}')
        prior=json.loads(old.read_text())
        if prior.get('graph_sha256')!=sha(graph) or prior.get('version_sha256')!=sha(version) or prior.get('wrapper_sha256')!=sha(tcl):
            raise RuntimeError('Existing timing database provenance does not match current synthesis inputs')
        if datetime.fromtimestamp(database.stat().st_mtime,timezone.utc)<datetime.fromisoformat(prior['started_utc']):
            raise RuntimeError('Existing timing database predates its recorded analysis')
        reuse=True;started=prior['started_utc'];code=prior['exit_code']
        logtext=logpath.read_text(errors='replace') if logpath.exists() else ''
    else:
        started=datetime.now(timezone.utc).isoformat();code=None
        with logpath.open('wb') as log:
            try:code=subprocess.run(command,cwd=SHELL,stdout=log,stderr=subprocess.STDOUT,timeout=300).returncode
            except subprocess.TimeoutExpired:error='native report timed out'
        logtext=logpath.read_text(errors='replace')
    analysis_generated=code==0 and database.exists() and database.stat().st_size>0 and 'All was well!' in logtext
    analysis=read_timing_database(database) if analysis_generated else None
    clock=analysis['clock'] if analysis else {}
    target_mhz=100.0
    target_period_ps=1000000.0/target_mhz
    fmax=clock.get('fmax_mhz',0)
    user_setup_pass=analysis_generated and fmax>=target_mhz
    project_setup_pass=analysis_generated and clock.get('setup_wns_ps',-1)>=0
    hold_estimate_pass=analysis_generated and clock.get('hold_wns_ps',-1)>=0
    timing_pass=analysis_generated and project_setup_pass and hold_estimate_pass
    result='PASS' if timing_pass else ('PARTIAL_100MHZ_MET' if user_setup_pass else ('FAIL' if analysis_generated else 'UNAVAILABLE'))
    summary=dict(result=result,
                 scope='native EQ6HL45 synthesis timing analysis; no placement or routing; unconstrained IO groups are listed separately',
                 units='delays and slack in ps; Fmax in MHz',
                 checks=dict(user_100mhz_setup_pass=user_setup_pass,
                             user_100mhz_setup_margin_ps=round(target_period_ps-1000000.0/fmax) if fmax else None,
                             project_8ns_setup_pass=project_setup_pass,
                             project_8ns_setup_wns_ps=clock.get('setup_wns_ps'),
                             pre_route_hold_estimate_pass=hold_estimate_pass,
                             pre_route_hold_wns_ps=clock.get('hold_wns_ps'),
                             placed_routed_timing='NOT RUN'),
                 target=dict(minimum_user_fmax_mhz=target_mhz,
                             project_clock_period_ps=manifest['clock_constraint_ns']*1000,
                             minimum_project_setup_wns_ps=0,minimum_pre_route_hold_wns_ps=0),
                 timing=analysis)
    (audit/'timing_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    models=SHELL.parent/'Infrastructure/psk_intern/eHiChip6/EQ6HL45'
    proof=dict(result=summary['result'],exit_code=code,error=error,reused_existing_analysis=reuse,
               started_utc=started,completed_utc=datetime.now(timezone.utc).isoformat(),command=command,
               scope='native EQ6HL45 synthesized timing analysis; no placement or routing',
               timing_verdict='PASS' if timing_pass else ('PARTIAL' if user_setup_pass else ('FAIL' if analysis_generated else 'NOT VERIFIED')),
               Implementation_place_route='NOT RUN',Bitstream='NOT RUN',
               official_entry_sha256=sha(official),tool_sha256=sha(tool),wrapper_sha256=sha(tcl),
               source_manifest_sha256=sha(project/'project_manifest.json'),
               graph_sha256=sha(graph),version_sha256=sha(version),log_sha256=sha(audit/'console.log'),
               timing_models_sha256={p.name:sha(p) for p in models.glob('timing*.dat')},
               analysis_database=str(database) if database.exists() else None,
               analysis_database_sha256=sha(database) if database.exists() else None,
               textual_report=str(report) if report.exists() else None,
               textual_report_sha256=sha(report) if report.exists() else None,
               timing_summary=str(audit/'timing_summary.json'),timing_summary_sha256=sha(audit/'timing_summary.json'))
    (audit/'provenance.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(logtext[-1000:]);print(json.dumps(summary,indent=2));print(json.dumps(proof,indent=2))
    return 0 if timing_pass else 1


if __name__=='__main__':raise SystemExit(main())
