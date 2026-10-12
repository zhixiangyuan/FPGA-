from pathlib import Path
import csv,json,hashlib,zlib,sys
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def mem(p):return bytes(int(x,16) for x in p.read_text().splitlines())
def main(run):
 s=json.loads((run/'summary.json').read_text());assert s['result']=='PASS' and s['exit_code']==0
 text=(run/'transcript.log').read_text();assert all(x in text for x in ('V1_FULL_ECHO = PASS','V1_PRESSURE_RESET = PASS','V1_PARTIAL_RESET = PASS','Errors: 0')) and '** Fatal' not in text and '** Error' not in text
 for x in s['sources']:
  assert sha(run/Path(x['path']).name)==x['snapshot_sha256']
  if Path(x['path']).exists():assert sha(Path(x['path']))==x['sha256']
 g=run/'golden';assert sha(g/'sha256.json')==s['golden_sha256']
 for n,h in json.loads((g/'sha256.json').read_text()).items():assert sha(g/n)==h
 cases=json.loads((g/'cases.json').read_text());ins=mem(g/'incoming.mem');outs=mem(g/'outgoing.mem');app=mem(g/'payload.mem');badfcs=0
 for c in cases:
  w=ins[c['incoming_offset']:c['incoming_offset']+c['incoming_length']]
  if w[-4:]!=(zlib.crc32(w[8:-4])&0xffffffff).to_bytes(4,'little'):assert c['mutation']=='fcs';badfcs+=1
 def check(name,selected,kind):
  rows=list(csv.DictReader((run/name).open(newline='')));i=0;starts=[]
  for c in selected:
   n=c['outgoing_length'] if kind=='tx' else c['payload_length'];base=c['outgoing_offset'] if kind=='tx' else c['payload_offset'];blob=outs if kind=='tx' else app
   if kind=='tx':
    w=blob[base:base+n];assert w[:8]==bytes.fromhex('55555555555555d5') and w[-4:]==(zlib.crc32(w[8:-4])&0xffffffff).to_bytes(4,'little');assert w[-5]==c['tx_sn'];starts.append((c,int(rows[i]['cycle'])))
   for j in range(n):
    row=rows[i];assert int(row['case_id'])==c['id'] and int(row['byte_index'])==j and int(row['data'],16)==blob[base+j]
    if kind=='app':assert tuple(int(row[k]) for k in ('sop','eop','length','sn'))==(int(j==0),int(j+1==n),n,c['rx_sn'])
    i+=1
  assert i==len(rows);return i,starts
 tx=[c for c in cases if c['action']==0];apps=[c for c in cases if c['action'] in (0,6)]
 txbytes,starts=check('actual_tx.csv',tx,'tx');appbytes,_=check('actual_app.csv',apps,'app');gaps=[]
 for (a,ca),(b,cb) in zip(starts,starts[1:]):
  if a['epoch']==b['epoch']:assert cb-ca>=125000;gaps.append(cb-ca)
 decisions=list(csv.DictReader((run/'decisions.csv').open(newline='')))
 selected=[c for c in cases if c['action'] not in (5,7) and not(c['name'].startswith('pressure_retained_') and c['rx_sn']!=16)]
 assert len(decisions)==308 and [int(row['case_id']) for row in decisions]==[c['id'] for c in selected]
 epoch=-1;stored=sent=0;counts={}
 for c in cases:
  if c['epoch']!=epoch:epoch=c['epoch'];stored=sent=0
  stored+=int(c['action'] in (0,6));sent+=int(c['action']==0);counts[c['id']]=(stored,sent)
 for row in decisions:
  c=cases[int(row['case_id'])];assert (int(row['psn']),int(row['valid']),int(row['missing']))==(c['expected_psn'],int(c['expected_valid']),c['expected_missing'])
  assert (int(row['stored']),int(row['sent']))==counts[c['id']]
 assert len(tx)==295 and len(apps)==296 and txbytes==22840 and appbytes==2520
 assert len([c for c in cases if c['name'].startswith('wrap_')])==256
 assert any(c['rx_sn']!=c['tx_sn'] for c in tx)
 assert (run/'waves.wlf').stat().st_size>0
 result={'result':'PASS','scope':'candidate eight-port GMII echo through actual SN-gated application','golden_cases':len(cases),'tx_frames':len(tx),'tx_bytes':txbytes,'app_frames':len(apps),'app_bytes':appbytes,'SN_wrap':256,'independent_TX_SN_confirmed':True,'BAG_gaps_checked':len(gaps),'minimum_BAG_cycles':min(gaps),'decisions_compared':len(decisions),'protocol_rejections':sum(c['action']==3 for c in cases),'SN_rejections':sum(c['action']==1 for c in cases),'SN0_controls':sum(c['action']==2 for c in cases),'FCS_rejections':badfcs,'pressure_retained':6,'capacity_drop':1,'reset_cancel':1,'partial_reset':1,'artifact_hashes':{p.name:sha(p) for p in run.iterdir() if p.is_file() and p.name!='verification.json'}}
 (run/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main(Path(sys.argv[1]).resolve())
