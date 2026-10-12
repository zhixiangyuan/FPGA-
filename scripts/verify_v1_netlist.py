"""Independent real VO provenance, wire bytes, actual commits and PSN audit."""
from pathlib import Path
import json,csv,hashlib,zlib,sys
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def mem(p):return bytes(int(x,16) for x in p.read_text().splitlines())
def main(run):
 s=json.loads((run/'summary.json').read_text());proof=json.loads((run/'provenance.json').read_text());assert s['result']=='PASS' and s['exit_code']==0
 assert not proof['RTL_DUT_compiled'] and not proof['force_used'] and proof['read_only_actual_VO_probes']
 assert sorted(Path(p).name for p in proof['compile_sources'])==sorted(['AFDX_top.vo','tb_v1_netlist.sv','altera_primitives.v','220model.v','stratix_atoms.v'])
 text=(run/'transcript.log').read_text();assert all(m in text for m in ('V1_REAL_NETLIST = PASS','V1_NETLIST_PRESSURE = PASS','V1_NETLIST_PARTIAL_RESET = PASS','Errors: 0')) and '** Fatal' not in text and '** Error' not in text
 for x in s['sources']:
  assert sha(run/Path(x['path']).name)==x['snapshot_sha256']
  if Path(x['path']).exists():assert sha(Path(x['path']))==x['sha256']
 g=run/'golden';assert sha(g/'sha256.json')==s['golden_sha256']
 for n,h in json.loads((g/'sha256.json').read_text()).items():assert sha(g/n)==h
 cases=json.loads((g/'cases.json').read_text());out=mem(g/'outgoing.mem');incoming=mem(g/'incoming.mem');expected_tx=[c for c in cases if c['action']==0];apps=[c for c in cases if c['action'] in (0,6)]
 rows=list(csv.DictReader((run/'actual_tx.csv').open(newline='')));i=0;starts=[];ends=[]
 for c in expected_tx:
  blob=out[c['outgoing_offset']:c['outgoing_offset']+c['outgoing_length']];start=int(rows[i]['cycle']);starts.append((c,start))
  assert blob[-5]==c['tx_sn'] and blob[-4:]==(zlib.crc32(blob[8:-4])&0xffffffff).to_bytes(4,'little')
  for b in range(c['outgoing_length']):
   row=rows[i];assert (int(row['case_id']),int(row['byte_index']),int(row['data'],16))==(c['id'],b,blob[b]);assert int(row['cycle'])==start+b;i+=1
  ends.append((c,int(rows[i-1]['cycle'])))
 assert i==len(rows)==22840 and len(starts)==295
 commits=list(csv.DictReader((run/'app_commits.csv').open(newline='')));assert len(commits)==len(apps)==296
 for row,c in zip(commits,apps):assert (int(row['case_id']),int(row['length']),int(row['rx_sn']))==(c['id'],c['payload_length'],c['rx_sn'])
 epoch=-1;app=tx=0;counts={}
 for c in cases:
  if c['epoch']!=epoch:epoch=c['epoch'];app=tx=0
  app+=c['action'] in (0,6);tx+=c['action']==0;counts[c['id']]=(app,tx)
 decisions=list(csv.DictReader((run/'decisions.csv').open(newline='')))
 selected=[c for c in cases if c['action'] not in (5,7) and not(c['name'].startswith('pressure_retained_') and c['rx_sn']!=16)]
 assert len(decisions)==308 and [int(r['case_id']) for r in decisions]==[c['id'] for c in selected]
 for r,c in zip(decisions,selected):assert (int(r['psn']),int(r['valid']),int(r['commits']),int(r['sent']))==(c['expected_psn'],int(c['expected_valid']),*counts[c['id']])
 inputs=list(csv.DictReader((run/'input_events.csv').open(newline='')));assert [int(r['case_id']) for r in inputs]==list(range(len(cases)))
 bad=0
 for row,c in zip(inputs,cases):
  assert int(row['action'])==c['action'] and int(row['bytes'])==(100 if c['action']==7 else c['incoming_length'])
  assert int(row['end_cycle'])-int(row['start_cycle'])+1==int(row['bytes'])
  blob=incoming[c['incoming_offset']:c['incoming_offset']+c['incoming_length']]
  if blob[-4:]!=(zlib.crc32(blob[8:-4])&0xffffffff).to_bytes(4,'little'):assert c['mutation']=='fcs';bad+=1
 gaps=[b-a for (ca,a),(cb,b) in zip(starts,starts[1:]) if ca['epoch']==cb['epoch']];assert len(gaps)==289 and min(gaps)>=125000 and max(gaps)<=137500
 assert (run/'waves.wlf').stat().st_size>0
 result={'result':'PASS','scope':'real synthesized candidate AFDX_top; exact external bytes plus real application RAM commits and retained PSN','golden_cases':len(cases),'external_TX_frames':len(starts),'external_TX_bytes':len(rows),'actual_app_bank_commits':len(commits),'committed_payload_bytes_metadata':sum(c['payload_length'] for c in apps),'external_echo_payload_bytes':sum(c['payload_length'] for c in expected_tx),'raw_internal_app_byte_compare':'covered by frozen-current RTL run; not fabricated for optimized VO nets','SN_wrap':256,'actual_PSN_decisions':len(decisions),'BAG_gaps':len(gaps),'min_BAG_cycles':min(gaps),'max_BAG_cycles':max(gaps),'intentional_FCS_error':bad,'pressure_retained':6,'capacity_drop':1,'reset_cancel':1,'partial_reset':1,'diagnostic_missing_counter':'optimized away; not claimed as a physical observable','POST_SYNTH_TIMING':'NOT VERIFIED','EQ6_NATIVE_NETLIST_EQUIVALENCE':'NOT VERIFIED','artifact_hashes':{p.name:sha(p) for p in run.iterdir() if p.is_file() and p.name!='verification.json'}}
 (run/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='artifact_hashes'},indent=2))
if __name__=='__main__':main(Path(sys.argv[1]).resolve())
