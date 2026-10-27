"""Verify identical inputs and isolate the one arbiter change before comparing."""
from pathlib import Path
import argparse,json,re
from run_competition import ROOT,sha
from run_service_pressure import verify

def main():
    p=argparse.ArgumentParser();p.add_argument('baseline',type=Path);p.add_argument('candidate',type=Path)
    p.add_argument('--before-project',type=Path);p.add_argument('--after-project',type=Path)
    p.add_argument('--out',type=Path,default=ROOT/'reports/SERVICE_PRESSURE_COMPARISON_20261027.json');a=p.parse_args()
    b=json.loads((a.baseline/'summary.json').read_text());c=json.loads((a.candidate/'summary.json').read_text())
    assert b['result']==c['result']=='PASS' and b['backend']==c['backend']=='RTL'
    assert b['golden']==c['golden'] and b['clock_ns']==c['clock_ns']==8 and b['BAG_cycles']==c['BAG_cycles']==125000
    bi={Path(n).name:h for n,h in b['inputs'].items()};ci={Path(n).name:h for n,h in c['inputs'].items()}
    assert len(bi)==len(b['inputs']) and len(ci)==len(c['inputs']) and bi.keys()==ci.keys()
    changed=[n for n in bi if bi[n]!=ci[n]]
    assert changed==['afdx_service_tx_arbiter_615a.v'],changed
    for folder,proof in ((a.baseline,b),(a.candidate,c)):
        for name,digest in proof['inputs'].items():assert sha(folder/Path(name).name)==digest,(folder,name)
        for name,digest in proof['golden'].items():assert sha(folder/'golden'/name)==digest
        expected={int(k):[bytes.fromhex(w) for w in v] for k,v in json.loads((folder/'golden/expected.json').read_text()).items()}
        assert verify(folder,expected)==proof['evidence'],'raw-output evidence changed'
    assert sha(a.baseline/'inputs.csv')==sha(a.candidate/'inputs.csv'),'offered timestamps or bytes differ'
    be,ce=b['evidence'],c['evidence']
    assert be['application_messages']==ce['application_messages']==24 and be['wire_frames']==ce['wire_frames']==27
    assert be['no_application_loss'] and ce['no_application_loss'] and be['no_duplicate_application_delivery'] and ce['no_duplicate_application_delivery']
    result=dict(result='PASS',baseline=str(a.baseline.resolve()),candidate=str(a.candidate.resolve()),
        comparison_verifier_sha256=sha(Path(__file__)),behavior_verifier_sha256=sha(ROOT/'scripts/run_service_pressure.py'),
        baseline_summary_sha256=sha(a.baseline/'summary.json'),candidate_summary_sha256=sha(a.candidate/'summary.json'),
        changed_source=changed[0],baseline_source_sha256=bi[changed[0]],candidate_source_sha256=ci[changed[0]],
        identical_Golden=True,identical_Testbench=True,identical_offered_timestamps=True,clock_ns=8,BAG_cycles=125000,
        metrics=dict(baseline=be,candidate=ce,
          delivered_throughput_gain_percent=(ce['payload_delivered_Mbps']/be['payload_delivered_Mbps']-1)*100,
          maximum_latency_reduction_percent=(1-ce['max_application_first_to_last_ns']/be['max_application_first_to_last_ns'])*100),
        scope='Engineering improvement under deliberate two-request management backlog; not a legal-peer BAG throughput claim or global worst-case proof',
        innovation='Eligibility before shared-resource reservation, extended from load VL to SNMP/SNTP with frame-atomic fair arbitration',
        algorithmic_novelty='NOT CLAIMED; inspectable project engineering improvement')
    if a.before_project or a.after_project:
        assert a.before_project and a.after_project
        projects=[a.before_project.resolve(),a.after_project.resolve()];manifests=[];runners=[];resources=[]
        for project in projects:
            manifests.append(json.loads((project/'project_manifest.json').read_text()))
            runners.append(json.loads((project/'synthesis_runner.json').read_text()))
            text=(project/'AFDXSUB.runs/synth_1/AFDXSUB_utilization_synth.rpt').read_text()
            resources.append({key:int(re.search(r'Total '+key+r'\s*:\s*(\d+)',text)[1]) for key in ('LUTs','FFs','CLBs','Memorys','Pins')})
        bm,cm=manifests;br,cr=runners
        assert br['result']==cr['result']=='PASS'
        for key in ('driver_sha256','optimization_technique','settings_reference_sha256'):assert br[key]==cr[key]
        for key in ('device','package','clock_constraint_ns','constraint_sha256'):assert bm[key]==cm[key]
        bs={r['canonical_source']:r['sha256'] for r in bm['sources']};cs={r['canonical_source']:r['sha256'] for r in cm['sources']}
        assert bs.keys()==cs.keys() and [n for n in bs if bs[n]!=cs[n]]==['rtl/afdx_service_tx_arbiter_615a.v']
        for project,manifest,simulation_inputs in zip(projects,manifests,(bi,ci)):
            for row in manifest['sources']:
                assert simulation_inputs[Path(row['canonical_source']).name]==row['sha256'],'performance/synthesis source mismatch'
                assert sha(project/row['snapshot'])==row['sha256'],'synthesis source snapshot changed'
        normalized=[]
        for project in projects:normalized.append((project/'AFDXSUB.qsf').read_text().replace(project.as_posix(),'__PROJECT__'))
        assert normalized[0]==normalized[1],'synthesis settings changed beyond project paths'
        result['same_synthesis_conditions']=True
        result['performance_sources_match_synthesis']=True
        result['resources']=dict(baseline=resources[0],candidate=resources[1],
            LUT_increase=resources[1]['LUTs']-resources[0]['LUTs'],FF_increase=resources[1]['FFs']-resources[0]['FFs'],
            LUT_increase_percent=(resources[1]['LUTs']/resources[0]['LUTs']-1)*100,
            baseline_manifest_sha256=sha(projects[0]/'project_manifest.json'),candidate_manifest_sha256=sha(projects[1]/'project_manifest.json'))
    a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['metrics'],indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
