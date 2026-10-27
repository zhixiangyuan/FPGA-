"""Engineering coverage audit, not submission-document generation.

Official explicit requirements are separated from undefined full-standard
certification and deliberately deferred submission materials.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,csv,json
from run_competition import ROOT,sha,sources

def read_proof(folder):
    path=ROOT/folder/'summary.json'
    if not path.exists():return dict(status='NOT_RUN',path=str(path))
    proof=json.loads(path.read_text(encoding='utf-8-sig'));mismatch=[]
    for name,h in proof.get('inputs',{}).items():
        p=Path(name) if Path(name).is_absolute() else ROOT/name
        if not p.is_file() or sha(p)!=h:mismatch.append(name)
    for name,h in proof.get('compiled',{}).items():
        if not Path(name).is_file() or sha(Path(name))!=h:mismatch.append(name)
    for name,h in proof.get('golden',{}).items():
        p=path.parent/'golden'/name
        if isinstance(h,str) and len(h)==64 and (not p.is_file() or sha(p)!=h):mismatch.append('golden/'+name)
    for field,names in (('vectors_sha256',('vectors.mem',)),('expected_sha256',('expected.json','expected.mem'))):
        if field in proof:
            candidates=[path.parent/n for n in names if (path.parent/n).is_file()]
            if len(candidates)!=1 or sha(candidates[0])!=proof[field]:mismatch.append(field)
    status='STALE' if mismatch else proof['result']
    return dict(status=status,path=str(path),sha256=sha(path),mismatches=mismatch,
                evidence=proof.get('evidence',{}),summary=proof)

def main():
    p=argparse.ArgumentParser();p.add_argument('--vo-run',required=True);p.add_argument('--management-vo',required=True);p.add_argument('--project',required=True)
    a=p.parse_args()
    runs=dict(system='build/logs/competition_010',receiver='build/logs/redundant_rx_007',
              capacity='build/logs/rx_capacity_001',parser='build/logs/multi_vl_rx_006',
              bag='build/logs/bag_profiles_001',management='build/logs/competition_mgmt_005',
              pressure='build/logs/service_pressure_011',vo=a.vo_run,management_vo=a.management_vo,
              snmp='build/logs/snmp_024',sntp='build/logs/sntp_003',rtc='build/logs/rtc_003',
              loader='build/logs/a615a_011',smoke='build/logs/competition_smoke_005')
    evidence={k:read_proof(v) for k,v in runs.items()}
    project=ROOT/a.project;manifest=json.loads((project/'project_manifest.json').read_text())
    synth=json.loads((project/'synthesis_runner.json').read_text());pack=json.loads((project/'database_mapping_provenance.json').read_text())
    current_synth=all(sha(ROOT/r['canonical_source'])==r['sha256']==sha(project/r['snapshot']) for r in manifest['sources'])
    native=json.loads((project/'native_timing/timing_summary.json').read_text())
    synth_ok=synth['result']==pack['result']=='PASS' and current_synth
    setup_ok=native['checks']['project_8ns_setup_pass']
    rows=[]
    def add(id,requirement,source,keys,scope,kind='DERIVED_FUNCTIONAL_CHECK',extra=True):
        states=[evidence[k]['status'] for k in keys]
        status='PASS_FOR_PROFILE' if all(x=='PASS' for x in states) and extra else 'OPEN'
        rows.append(dict(id=id,requirement=requirement,source=source,kind=kind,status=status,
                         evidence=keys,scope=scope))
    add('R01','FPGA RTL design, eLinx synthesis and post-synthesis functional simulation','Guide PDF p4/p8; Q13/Q46',
        ['vo','management_vo'],'actual complete exported netlist and original vendor compatibility primitives',extra=synth_ok)
    add('R02','tx_data input and rx_data output carry VLID plus original application payload','Q110/Q120/Q124/Q126',
        ['system','vo'],'two-byte big-endian VLID and 1..1471 bytes; continuous-valid burst boundary')
    add('R03','Independent A/B gigabit GMII MAC paths','Q3/Q59/Q95/Q111',
        ['system','vo'],'125MHz 8-bit, two self-written MAC TX/RX paths, same-clock PHY profile',extra=setup_ok)
    add('R04','Ethernet/IPv4/UDP framing, VLID/SN and <=1518-byte Ethernet frame','Guide PDF p5',
        ['system','parser','vo'],'independent byte/FCS oracle; 1/64/512/1471 payload lengths')
    add('R05','Reject malformed FCS/IP/UDP without delivering invalid application data','Guide PDF p4 high-integrity communication',
        ['parser','pressure','management_vo'],'valid/zero UDP checksum plus corrupted FCS/IP/UDP; rejected peer does not poison SN')
    add('R06','Per-network and per-VL sequence integrity, wrap, missing/duplicate/old frame handling','Guide PDF p4; XAPP1130 p9/p15',
        ['receiver','capacity','vo'],'PSN +1/+2, invalid SN updates PSN, 255->1; SN0 is non-delivered reset control')
    add('R07','A/B deduplication, skew and single-network failure/recovery','Q95; high-integrity requirement',
        ['receiver','system','vo'],'first valid copy; delayed B, PHY fault, lost network; 5ms skew, delayed SN0 and 256 reset generations')
    add('R08','Atomic buffering and scheduling without partial-message leakage','Guide PDF p4 buffer/send/receive management',
        ['system','pressure','vo'],'16 shared TX slots and 16 receive banks per network; malformed app messages rejected atomically')
    add('R09','BAG shaping and service/business scheduling','Guide PDF p4 ARINC664P7; XAPP1130 p6-p9',
        ['bag','system','pressure','management_vo'],'eight legal BAG values in real builder/MAC test; default integration profile 1ms; independent gate retained')
    perf=evidence['system']['evidence'];load=ROOT/runs['system']/'inputs.csv'
    offers=list(csv.DictReader(load.open()))[176:688] if load.exists() else []
    no_stall=len(offers)==512 and all(int(b['cycle'])-int(x['cycle'])==8000 for x,b in zip(offers,offers[1:]))
    add('R10','>=100Mbps application payload injection, stable without loss/overflow/blocking','Q58/Q95/Q120',
        ['system'],'512x1471 bytes, 16 VL, 8000-cycle offered interval; redundancy counted once',
        extra=no_stall and perf.get('application_payload_input_Mbps',0)>=100 and perf.get('application_payload_delivered_Mbps',0)>=100)
    add('R11','Application-to-application single-frame worst observed latency below 2ms','Q119/Q123/Q125',
        ['system','pressure','vo'],'input first byte to output last byte (conservative); declared admissible load only',
        extra=perf.get('max_application_first_to_last_ns',1e9)<2000000)
    add('R12','Same-VL, same-length latency range within tens of microseconds','Guide PDF p5; Q119',
        ['system','pressure'],'official gives no exact numeric threshold; 50us is an engineering check, not an official fixed limit',
        extra=perf.get('max_same_VL_same_length_range_ns',1e9)<=50000)
    add('R13','Minimum, maximum and at least two intermediate lengths; multi-VL concurrency','Q97',
        ['system'],'1,64,512,1471 payload bytes; variable lengths and sustained same-length window')
    add('R14','Configure 128 TX VLs, application stimulus injection','Guide PDF p5; Q120',
        ['system'],'all 128 business VLs actually transmit; parameters configure contiguous VL range at elaboration')
    add('R15','4096 RX VL support','Guide PDF p5; Q96',
        ['receiver','capacity'],'every VL gets SN1 and SN2 on both real GMII networks: 8192 application deliveries')
    add('R16','SNMP network management','Guide PDF p4; Q47/Q48',
        ['snmp','management','management_vo'],'SNMPv1 GET/GETNEXT/SET profile; six system objects, v2c limited request extension; SET persistence through netlist')
    add('R17','RTC synchronization with network time source','Guide PDF p4; Q47/Q48',
        ['rtc','sntp','management','management_vo'],'Q32.32 timebase, four timestamp SNTP, negative/timeout unit tests, real network synchronization')
    add('R18','Normal synthesis on supported eLinx device','Q121/Q122',
        [],'EQ6HL130/CSG484_H, no resource-score threshold',extra=synth_ok)
    add('R19','Self-written stimulus and independent verification','Q2/Q5/Q46/Q96',
        ['system','capacity','vo','management_vo'],'full RTL scope plus same-version SNMP/RTC management netlist test; no force, no scaled BAG')
    rows.append(dict(id='P01',requirement='ARINC664P7 communication functions required by the guide',
                     source='Guide PDF p4; Q47/Q48',kind='OFFICIAL_PROTOCOL_SCOPE',status='NOT_FULLY_VERIFIED',
                     evidence=['system','receiver','capacity','parser','bag','vo'],
                     scope='Declared-profile behaviors are tested, but no complete clause-by-clause protocol conformance audit exists. Formal certification is not stated as a contest requirement.'))
    rows.append(dict(id='W01',requirement='ARINC615A loading and ARINC665 format',source='Q96.2 overrides guide p4',
                     kind='WAIVED_HARD_REQUIREMENT',status='WAIVED',evidence=['loader'],scope='module implemented/tested; complete new-wrapper loading session remains unverified'))
    rows.append(dict(id='D01',requirement='Submission design/report/video materials',source='Guide PDF p6; Q112; current user instruction',
                     kind='DELIVERY_DEFERRED',status='DEFERRED_BY_USER',evidence=[],scope='not organized in this task'))
    rows.append(dict(id='L01',requirement='Hardware, place/route, full IO/hold physical timing, full EQ6 native equivalence',source='Guide PDF p8; Q46/Q80',
                     kind='OUTSIDE_REQUIRED_FUNCTIONAL_SCOPE',status='NOT_CLAIMED',evidence=[],scope='hold estimate -68ps and IO groups not fully constrained; do not claim physical sign-off'))
    comparison=ROOT/'reports/SERVICE_PRESSURE_COMPARISON_20261027.json'
    if comparison.exists():
        improvement=json.loads(comparison.read_text())
        rows.append(dict(id='I01',requirement='Measured isolation improvement under management backlog',
            source='Baseline/current same Golden, source manifest, settings, clock and BAG',kind='MEASURED_ENGINEERING_IMPROVEMENT',
            status='PASS_FOR_TESTED_WORKLOAD' if improvement['result']=='PASS' and improvement.get('same_synthesis_conditions') and improvement.get('performance_sources_match_synthesis') else 'NOT_RUN',
            evidence=[str(comparison.relative_to(ROOT))],scope='SNMP/SNTP descriptors reserve shared sender only when BAG eligible; exact workload and delta are recorded in the report',metrics=improvement.get('metrics',{})))
    functional=[r for r in rows if r['kind']=='DERIVED_FUNCTIONAL_CHECK'];open_rows=[r['id'] for r in functional if r['status']!='PASS_FOR_PROFILE']
    excluded_attempts=[]
    for folder in ('competition_smoke_vo_001','service_pressure_vo_001','management_netlist_vo_003'):
        path=ROOT/'build/logs'/folder/'summary.json'
        if path.exists():
            previous=json.loads(path.read_text(encoding='utf-8-sig'))
            excluded_attempts.append(dict(path=str(path),result=previous['result'],summary_sha256=sha(path),
                                          reason='Incomplete attempt; not counted as acceptance evidence.'))
    refs=list(Path('D:/FPGA').glob('*选题指南*.pdf'))+[Path('C:/Users/袁志祥/Downloads/FPGA创新大赛问题汇总 (3).xlsx')]
    refs+=list(Path('D:/FPGA/资料').glob('*V2.1.docx'))
    result=dict(result='DECLARED_PROFILE_CHECKS_PASS_PROTOCOL_SCOPE_OPEN' if not open_rows else 'INCOMPLETE',
                audited_utc=datetime.now(timezone.utc).isoformat(),audit_script_sha256=sha(Path(__file__)),open_functional_check_items=open_rows,
                open_protocol_scope=['P01'],official_numbered_checklist='NOT_PROVIDED; R01..R19 are project-derived engineering checks',
                source_notes='Local V2.1 copy has 2026 in its filename and 2025 on its cover; AFDX core requirements match the guide. Later workbook answers govern clarified requirements.',
                scope='engineering implementation/validation audit, not submission materials or complete protocol certification',
                official_sources={str(x):sha(x) for x in refs},canonical_sources={str(x.relative_to(ROOT)):sha(x) for x in sources()},
                requirements=rows,evidence=evidence,excluded_attempts=excluded_attempts,project=str(project),source_manifest_sha256=sha(project/'project_manifest.json'),
                synthesis_current=synth_ok,native_8ns_setup=setup_ok,timing=native,
                nominal_load_without_input_stalls=no_stall)
    target=ROOT/'reports/REQUIREMENTS_COVERAGE_20261027.json';target.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    lines=['# 官方要求工程覆盖核对','',f'结论：{result["result"]}。未闭合已拆分功能检查项：{", ".join(open_rows) or "无"}。协议规范范围仍有待逐条核对：P01。',
           '', 'R01～R19 是本工程根据官方资料拆分的检查项，并非官方发布的完整合规清单。19 项在声明配置内通过，不代表已完成全部比赛协议要求的无条件验收。正式认证并非官方明确要求。',
           '', '本文件用于工程核对；提交材料按当前要求暂缓整理。',
           '', '| ID | 要求 | 依据 | 状态 | 证据 | 范围 |','|---|---|---|---|---|---|']
    for r in rows:lines.append('| '+' | '.join((r['id'],r['requirement'],r['source'],r['status'],', '.join(r['evidence']),r['scope']))+' |')
    lines+=['','详细源码、原始摘要和官方文件 SHA-256 见 `REQUIREMENTS_COVERAGE_20261027.json`。',
            '', '未完成的旧尝试不计入通过：'+', '.join(Path(x['path']).parent.name+'='+x['result'] for x in excluded_attempts)+'。',
            '', '实现侧仍限制为已声明地址、端口、单时钟与有限缓存负载。正式规范未指定版本/必测子集；未声称完整 ARINC 认证、任意负载无损或外部设备互操作。']
    (ROOT/'reports/官方要求工程覆盖核对_20261027.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(dict(result=result['result'],open_functional_check_items=open_rows,open_protocol_scope=result['open_protocol_scope'],evidence_status={k:v['status'] for k,v in evidence.items()}),indent=2))
    return 0 if not open_rows else 1

if __name__=='__main__':raise SystemExit(main())
