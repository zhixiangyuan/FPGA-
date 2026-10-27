"""Recheck saved acceptance evidence without rerunning or changing the RTL."""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import csv, hashlib, json, re, subprocess, sys, tempfile, zipfile, zlib
from run_competition import ROOT, sha, sources, verify as verify_system
from run_competition_smoke import generate as generate_smoke, verify as verify_smoke
from frozen_frame_reference import make_client, wire_for
from audit_requirements import read_proof

def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def packets(path):
    result=[]; data=bytearray()
    for row in csv.DictReader(path.open()):
        if int(row['sop']): assert not data
        data.append(int(row['data']))
        if int(row['eop']): result.append(bytes(data)); data.clear()
    assert not data
    return result

def ethernet(wire):
    assert wire[:8]==bytes.fromhex('55555555555555d5')
    assert 64<=len(wire)-8<=1518
    assert wire[-4:]==zlib.crc32(wire[8:-4]).to_bytes(4,'little')

def main():
    folder=ROOT/'build/final_acceptance_review';folder.mkdir(exist_ok=True)
    coverage=load(ROOT/'reports/REQUIREMENTS_COVERAGE_20261027.json')
    checks=[]
    def check(name,action):
        try:
            details=action();checks.append(dict(name=name,status='PASS',details=details))
        except Exception as exc:
            checks.append(dict(name=name,status='FAIL',error=repr(exc)))

    def fingerprints():
        assert coverage['audit_script_sha256']==sha(ROOT/'scripts/audit_requirements.py')
        assert all(sha(Path(p))==h for p,h in coverage['official_sources'].items())
        assert all(sha(ROOT/p)==h for p,h in coverage['canonical_sources'].items())
        assert {str(p.relative_to(ROOT)):sha(p) for p in sources()}==coverage['canonical_sources']
        for row in load(ROOT/'FROZEN_CORE_MANIFEST.json'):
            assert sha(ROOT/'vendor/frozen'/Path(row['snapshot']).name)==row['sha256']
        statuses={}
        for key,entry in coverage['evidence'].items():
            summary=Path(entry['path']);assert sha(summary)==entry['sha256']
            proof=read_proof(summary.parent);assert proof['status']=='PASS',(key,proof['mismatches'])
            s=proof['summary'];assert s.get('exit_code',0)==0
            log=(summary.parent/'transcript.log').read_text(errors='replace')
            assert re.search(r'\b[A-Z0-9_]*PASS\b',log),key
            assert not re.search(r'^\s*#?\s*\*\* (?:Error|Fatal)',log,re.M),key
            statuses[key]='PASS'
        return dict(evidence_status=statuses,frozen_sources_unchanged=True)
    check('Source, official-file, Golden and saved-run fingerprints',fingerprints)

    def toolchain():
        project=ROOT/'build/elinx/AFDXSUB_011';manifest=load(project/'project_manifest.json')
        runner=load(project/'synthesis_runner.json');pack=load(project/'database_mapping_provenance.json')
        export_dir=ROOT/'build/logs/eda_stage2_export_014';export=load(export_dir/'provenance.json')
        assert export['source_project']==str(project)
        for obj in (runner,pack,export):assert obj['source_manifest_sha256']==sha(project/'project_manifest.json')
        assert export['synthesis_runner_sha256']==sha(project/'synthesis_runner.json')
        assert export['database_mapping_provenance_sha256']==sha(project/'database_mapping_provenance.json')
        assert export['delivered_netlist_sha256']==sha(export_dir/'AFDX_top.vo')
        assert export['export_log_sha256']==sha(export_dir/'export.log')
        assert runner['settings_qsf_sha256']==sha(project/'AFDXSUB.qsf')
        assert manifest['constraint_sha256']==sha(project/'AFDXSUB.srcs/constrs_1/new/clock_125mhz.edc')
        for row in manifest['sources']:
            assert sha(ROOT/row['canonical_source'])==row['sha256']==sha(project/row['snapshot'])
        for obj in (runner,pack):
            for name,h in obj['artifacts'].items():
                # The exporter/timing tool appends its stage status to this log.
                if name!='AFDXSUB.flow.rpt': assert sha(project/'AFDXSUB.runs/synth_1'/name)==h,name
        for obj in (runner,pack,export):
            if 'tool_sha256' in obj:assert sha(Path(obj['command'][0]))==obj['tool_sha256']
        assert sha(Path(pack['pack_command'][0]))==pack['pack_tool_sha256']
        native=load(project/'native_timing/provenance.json')
        assert native['source_manifest_sha256']==sha(project/'project_manifest.json')
        assert sha(Path(native['analysis_database']))==native['analysis_database_sha256']
        assert sha(Path(native['timing_summary']))==native['timing_summary_sha256']
        assert sha(project/'native_timing/console.log')==native['log_sha256']
        for key in ('vo','management_vo'):
            s=coverage['evidence'][key]['summary']
            assert s['provenance_sha256']==sha(export_dir/'provenance.json')
            assert s['compiled'][str(export_dir/'AFDX_top.vo')]==export['delivered_netlist_sha256']
        return dict(netlist_sha256=export['delivered_netlist_sha256'],model=export['model_backend'],
                    EQ6_native_equivalence='NOT VERIFIED',physical_timing='NOT SIGNED OFF')
    check('RTL to synthesis database to actual VO provenance',toolchain)

    def system():
        run=ROOT/'build/logs/competition_010';actual=verify_system(run)
        assert actual==load(run/'summary.json')['evidence']
        rows=list(csv.DictReader((run/'inputs.csv').open()))[176:688]
        assert len(rows)==512 and all(int(b['cycle'])-int(a['cycle'])==8000 for a,b in zip(rows,rows[1:]))
        return actual
    check('Full application raw-output and performance recalculation',system)

    def capacity():
        run=ROOT/'build/logs/rx_capacity_001'
        actual=packets(run/'application.csv');expected=[bytes.fromhex(x) for x in load(run/'golden/expected.json')]
        assert actual==expected and len(actual)==8192
        counts=Counter(int.from_bytes(p[:2],'big') for p in actual)
        assert counts=={v:2 for v in range(0x1234,0x2234)}
        wire=bytes.fromhex(''.join((run/'golden/wire.mem').read_text().split()))
        assert len(wire)==8192*72
        for i in range(8192):ethernet(wire[i*72:(i+1)*72])
        return dict(VLs=4096,application_deliveries=8192,wire_frames_per_network=8192)
    check('All 4096 receive VLs and input frame CRCs',capacity)

    def receiver():
        run=ROOT/'build/logs/redundant_rx_007';s=load(run/'summary.json')
        assert sha(run/'expected.json')==s['expected_sha256'] and sha(run/'vectors.mem')==s['vectors_sha256']
        actual=packets(run/'rx_unit.csv');assert actual==[bytes.fromhex(x) for x in load(run/'expected.json')]
        assert len(actual)==s['application_deliveries']
        return dict(vectors=s['vectors'],application_deliveries=len(actual))
    check('Per-VL integrity and redundancy raw-output oracle',receiver)

    def bag():
        run=ROOT/'build/logs/bag_profiles_001';rows=list(csv.DictReader((run/'events.csv').open()))
        expected=b''.join(wire_for(make_client(i,1,1+i%2)[0]) for i in range(16))
        assert bytes.fromhex(''.join((run/'wire.mem').read_text().split()))==expected and len(rows)==16
        gaps=[]
        for n in range(8):
            a,b=rows[2*n:2*n+2];gap=int(b['start'])-int(a['start']);required=125000<<n
            assert int(a['bag'])==int(b['bag'])==required and required<=gap<=required+128;gaps.append(gap)
        return dict(BAG_ms=[1,2,4,8,16,32,64,128],observed_gap_cycles=gaps)
    check('Eight real BAG timers and wire bytes',bag)

    def smoke():
        run=ROOT/'build/logs/competition_smoke_vo_003'
        with tempfile.TemporaryDirectory(dir=folder) as temp:
            golden=Path(temp)/'golden';expected,wires=generate_smoke(golden)
            for p in golden.iterdir():assert sha(p)==sha(run/'golden'/p.name)
            result=verify_smoke(run,expected,wires)
        assert result==load(run/'summary.json')['evidence'];return result
    check('Current VO application output and independent wire oracle',smoke)

    def management():
        run=ROOT/'build/logs/management_netlist_vo_004'
        expected={int(k):list(map(bytes.fromhex,v)) for k,v in load(run/'golden/expected.json').items()}
        data=bytes.fromhex(''.join((run/'network_tx.mem').read_text().split()))
        rows=list(csv.DictReader((run/'frames.csv').open()));starts=[]
        for row in rows:
            vl=int(row['vl']);size=int(row['bytes']);wire=data[:size];data=data[size:]
            ethernet(wire);assert wire==expected[vl].pop(0)
            if vl==0x12b4:starts.append(int(row['start']))
        assert not data and len(rows)==3 and all(not x for x in expected.values())
        assert len(starts)==2 and starts[1]-starts[0]>=125000
        assert not (run/'application_rx.mem').read_text().strip()
        return dict(frames=3,SNMP_response_gap_cycles=starts[1]-starts[0],full_wire_oracle=True)
    check('Current VO SNMP SET/GET, SNTP and CRC oracle',management)

    def pressure():
        out=folder/'performance_recalculated.json'
        result=subprocess.run([sys.executable,str(ROOT/'scripts/compare_service_pressure.py'),
            'build/logs/service_pressure_010','build/logs/service_pressure_011',
            '--before-project','build/elinx/AFDXSUB_010','--after-project','build/elinx/AFDXSUB_011',
            '--out',str(out)],cwd=ROOT,capture_output=True,text=True)
        assert result.returncode==0,result.stderr
        actual=load(out);assert actual==load(ROOT/'reports/SERVICE_PRESSURE_COMPARISON_20261027.json')
        return dict(throughput_gain_percent=actual['metrics']['delivered_throughput_gain_percent'],
                    maximum_latency_reduction_percent=actual['metrics']['maximum_latency_reduction_percent'],
                    same_synthesis_conditions=actual['same_synthesis_conditions'])
    check('Same-input performance and synthesis-resource comparison',pressure)

    def archive():
        index=load(ROOT/'reports/COMPETITION_EVIDENCE_ARCHIVE_20261027.json');path=Path(index['archive'])
        assert sha(path)==index['archive_sha256']
        with zipfile.ZipFile(path) as z:
            raw=z.read('EVIDENCE_SHA256_MANIFEST.json');assert hashlib.sha256(raw).hexdigest()==index['manifest_sha256']
            manifest=json.loads(raw)['files'];assert len(manifest)==index['files']
            for name,row in manifest.items():assert hashlib.sha256(z.read(name)).hexdigest()==row['sha256'],name
            for name,h in coverage['canonical_sources'].items():assert manifest[name.replace('\\','/')]['sha256']==h
        return dict(files=index['files'],archive_sha256=index['archive_sha256'],all_contents_rehashed=True)
    check('Private archive integrity and archived RTL identity',archive)

    failed=[c['name'] for c in checks if c['status']=='FAIL']
    report=dict(result='PASS_FOR_DECLARED_PROFILE_PROTOCOL_SCOPE_OPEN' if not failed else 'FAIL',
        reviewed_utc=datetime.now(timezone.utc).isoformat(),reviewed_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        verifier_sha256=sha(Path(__file__)),coverage_report_sha256=sha(ROOT/'reports/REQUIREMENTS_COVERAGE_20261027.json'),
        RTL_unchanged=all(sha(ROOT/p)==h for p,h in coverage['canonical_sources'].items()),checks=checks,failed_checks=failed,
        findings=[dict(id='F01',severity='ACCEPTANCE_SCOPE',status='OPEN',
            detail='The guide requires ARINC664P7 communication functions. R01..R19 are project-derived checks, not an official complete checklist. Declared-profile tests pass; complete protocol clause coverage remains unverified. Formal certification is not an explicit contest requirement.'),
            dict(id='F02',severity='REPORTING',status='CORRECTED',detail='Coverage wording now explicitly retains P01 as an open protocol scope instead of implying complete contest conformance.')],
        remaining_exclusions=['complete protocol clause coverage','external-system interoperability','physical timing sign-off','submission materials deferred by user'])
    (ROOT/'reports/FINAL_ACCEPTANCE_REVIEW_20261027.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(dict(result=report['result'],failed_checks=failed,checks=[dict(name=c['name'],status=c['status'],error=c.get('error')) for c in checks]),indent=2))
    return bool(failed)

if __name__=='__main__':raise SystemExit(main())
