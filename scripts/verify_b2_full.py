"""File-level independent comparison of final application bytes and SN decisions."""
from pathlib import Path
import csv,hashlib,json,sys,zlib

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def mem(p):return bytes(int(x,16) for x in p.read_text().splitlines())
def main(run):
    run=run.resolve();s=json.loads((run/'summary.json').read_text())
    assert s['result']=='PASS' and s['exit_code']==0
    t=(run/'transcript.log').read_text()
    assert 'B2_FULL_SN_PROTOCOL = PASS' in t and 'B2_SN_CAPACITY_RESET = PASS' in t
    assert 'Errors: 0' in t and '** Fatal' not in t and '** Error' not in t
    for x in s['sources']:
        assert sha(Path(x['path']))==x['sha256']
        assert sha(run/Path(x['path']).name)==x['snapshot_sha256']
    g=run/'golden';assert sha(g/'sha256.json')==s['golden_sha256']
    for n,h in json.loads((g/'sha256.json').read_text()).items():assert sha(g/n)==h
    cases=json.loads((g/'cases.json').read_text());wire=mem(g/'wire.mem');app=mem(g/'payload.mem')
    crc_bad=0
    for c in cases:
        w=wire[c['wire_offset']:c['wire_offset']+c['wire_length']]
        if w[-4:]!=(zlib.crc32(w[8:-4])&0xffffffff).to_bytes(4,'little'):
            assert c['mutation']=='fcs';crc_bad+=1
    def check_csv(filename,selected,key,length_key,offset_key,blob):
        rows=list(csv.DictReader((run/filename).open(newline='')));i=0
        for c in selected:
            for b in range(c[length_key]):
                row=rows[i];assert int(row['case_id'])==c['id'] and int(row['byte_index'])==b
                assert int(row['data'],16)==blob[c[offset_key]+b]
                if key=='app':
                    assert int(row['sop'])==int(b==0) and int(row['eop'])==int(b+1==c[length_key])
                    assert int(row['length'])==c[length_key] and int(row['sn'])==c['sn']
                i+=1
        assert i==len(rows);return i
    tx_cases=[c for c in cases if c['source']=='B1']
    app_cases=[c for c in cases if c['action']==0 and c['name']!='accepted_reset_cancel_16']
    txbytes=check_csv('actual_tx_gmii.csv',tx_cases,'tx','wire_length','wire_offset',wire)
    appbytes=check_csv('actual_payload.csv',app_cases,'app','payload_length','payload_offset',app)
    decisions=list(csv.DictReader((run/'sn_decisions.csv').open(newline='')))
    expected_decisions=[c for c in cases if not c['name'].startswith('pressure_') and
                        c['name'] not in ('capacity_drop_14','accepted_reset_cancel_16')]
    assert len(decisions)==len(expected_decisions)
    epoch=-1;accepted=rejected=controls=delivered=0;lookup={}
    for c in cases:
        if c['epoch']!=epoch:epoch=c['epoch'];accepted=rejected=controls=delivered=0
        if c['action']==0:
            accepted+=1
            if c['name']!='accepted_reset_cancel_16':delivered+=1
        if c['action']==1:rejected+=1
        if c['action']==2:controls+=1
        lookup[c['id']]=(accepted,rejected,controls,delivered)
    for row,c in zip(decisions,expected_decisions):
        assert int(row['case_id'])==c['id'] and int(row['action'])==c['action']
        assert int(row['psn'])==c['expected_psn'] and int(row['psn_valid'])==c['expected_psn_valid']
        assert int(row['missing'])==c['expected_missing']
        assert tuple(int(row[k]) for k in ('accepted','rejected','control','delivered'))==lookup[c['id']]
    wlf=run/'waves.wlf';assert wlf.stat().st_size>0
    result={'result':'PASS','scope':'SN-gated application delivery, approved single-VL profile',
        'run':str(run),'real_b1_tx_frames':len(tx_cases),'gmii_bytes':txbytes,
        'application_frames':len(app_cases),'application_bytes':appbytes,
        'sn_decisions_compared':len(decisions),'golden_cases':len(cases),
        'sn_wrap_frames':256,'intentional_fcs_errors':crc_bad,
        'sn_rejections':sum(c['action']==1 for c in cases),
        'sn_controls':sum(c['action']==2 for c in cases),
        'protocol_rejections':sum(c['action']==3 for c in cases),
        'capacity_drop':1,'reset_cancel':1,
        'artifact_hashes':{n:sha(run/n) for n in ('waves.wlf','actual_tx_gmii.csv','actual_payload.csv','sn_decisions.csv','transcript.log')}}
    (run/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main(Path(sys.argv[1]))
