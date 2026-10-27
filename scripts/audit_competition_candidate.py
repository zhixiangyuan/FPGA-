"""Read-only provenance audit; write a compact, current-source evidence index."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, json, re
from run_competition import ROOT, sources, sha

def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--system',type=Path,required=True)
    parser.add_argument('--receiver',type=Path,required=True)
    parser.add_argument('--management',type=Path,required=True)
    parser.add_argument('--rtl-smoke',type=Path,required=True)
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--vo-smoke',type=Path,required=True)
    parser.add_argument('--out',type=Path,default=ROOT/'reports/COMPETITION_CANDIDATE_20261027.json')
    args=parser.parse_args();runs={};errors=[]
    for label,path in (('system',args.system),('receiver',args.receiver),('management',args.management),
                       ('rtl_smoke',args.rtl_smoke),('vo_smoke',args.vo_smoke)):
        if path is None:continue
        path=path.resolve();proof=load(path/'summary.json')
        if proof['result']!='PASS':errors.append(f'{label}: result is {proof["result"]}')
        mismatches=[]
        for name,digest in proof['inputs'].items():
            source=Path(name) if Path(name).is_absolute() else ROOT/name
            if not source.is_file() or sha(source)!=digest:mismatches.append(name)
        if mismatches:errors.append(f'{label}: current inputs differ {mismatches}')
        runs[label]=dict(path=str(path),summary_sha256=sha(path/'summary.json'),result=proof['result'],
                         input_mismatches=mismatches,evidence=proof.get('evidence',{}))
        for field in ('vectors','application_deliveries','VLs_exercised','recovery_timeout_test'):
            if field in proof:runs[label][field]=proof[field]
    frozen=load(ROOT/'FROZEN_CORE_MANIFEST.json')
    frozen_ok=all(sha(ROOT/'vendor/frozen'/Path(r['snapshot']).name)==r['sha256'] for r in frozen)
    if not frozen_ok:errors.append('frozen core hashes differ')
    project=args.project.resolve();manifest=load(project/'project_manifest.json')
    for row in manifest['sources']:
        if sha(ROOT/row['canonical_source'])!=row['sha256'] or sha(project/row['snapshot'])!=row['sha256']:
            errors.append(f'synthesis source mismatch: {row["canonical_source"]}')
    synthesis=load(project/'synthesis_runner.json');packing=load(project/'database_mapping_provenance.json')
    if synthesis['result']!='PASS' or packing['result']!='PASS':errors.append('synthesis/packing is not PASS')
    family=project.name.split('_')[0];util=project/f'{family}.runs/synth_1/{family}_utilization_synth.rpt'
    text=util.read_text(errors='replace');resources={}
    for key in ('LUTs','FFs','CLBs','Memorys','DSPs','PLLs','Pins'):
        match=re.search(r'Total '+key+r'\s*:\s*(\d+)',text)
        if match:resources[key]=int(match[1])
    timing_path=project/'native_timing/timing_summary.json'
    timing=load(timing_path) if timing_path.exists() else dict(result='NOT RUN')
    if not timing.get('checks',{}).get('project_8ns_setup_pass',False):
        errors.append('native project 8ns setup is not verified as passing')
    system=load(args.system/'summary.json')
    evidence=system['evidence']
    input_rows=list(__import__('csv').DictReader((args.system/'inputs.csv').open()))[176:688]
    offered_cycles=[int(r['cycle']) for r in input_rows]
    nominal_load_not_blocked=all(b-a==8000 for a,b in zip(offered_cycles,offered_cycles[1:]))
    if not nominal_load_not_blocked:errors.append('continuous offered load encountered input stalls')
    if evidence['application_payload_delivered_Mbps']<100:errors.append('payload throughput below 100Mbps')
    proof=dict(date='2026-10-27',audited_utc=datetime.now(timezone.utc).isoformat(),
               result='PASS_FOR_DECLARED_SCOPE' if not errors else 'FAIL',errors=errors,
               sources={str(p.relative_to(ROOT)):sha(p) for p in sources()},frozen_core_unchanged=frozen_ok,
               tests=runs,synthesis=dict(project=str(project),manifest_sha256=sha(project/'project_manifest.json'),
                                        runner_sha256=sha(project/'synthesis_runner.json'),
                                        packing_sha256=sha(project/'database_mapping_provenance.json'),
                                        resources=resources,device=manifest['device'],package=manifest['package']),
               performance=evidence,continuous_load_input_interval_8000_cycles_without_stalls=nominal_load_not_blocked,
               timing=timing,limitations=dict(full_615A_sessions_on_new_wrapper='NOT RUN',
                    EQ6_native_mapped_equivalence='NOT VERIFIED',place_route='NOT RUN',physical_IO_timing='NOT VERIFIED',
                    arbitrary_unbounded_bursts='NOT GUARANTEED',protocol_certification='NOT CLAIMED'),
               scope='source-bound application dual-network functional/VO candidate with native 8ns setup; not full protocol certification or physical timing sign-off')
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(proof,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(dict(result=proof['result'],errors=errors,resources=resources,
                          delivered_Mbps=evidence['application_payload_delivered_Mbps'],timing=timing.get('result'),
                          report=str(args.out)),indent=2))
    return 0 if not errors else 1

if __name__=='__main__':raise SystemExit(main())
