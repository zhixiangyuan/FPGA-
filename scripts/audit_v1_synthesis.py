"""Read real GUI smoke artifacts. Never invoke synthesis, fitting or EDA."""
from pathlib import Path
import hashlib,json,re
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 run=ROOT/'runs/elinx_001';p=run/'AFDXV1';s=p/'AFDXV1.runs/synth_1';manifest=json.loads((run/'project_manifest.json').read_text())
 for row in manifest['sources']:assert sha(Path(row['original']))==row['sha256'] and sha(Path(row['snapshot']))==row['snapshot_sha256']
 util=(s/'AFDXV1_utilization_synth.rpt').read_text();assert 'Synthesis Status : Successful' in util and 'Top-level Entity Name : AFDX_top' in util
 assert 'device_name="EQ6HL45"' in (s/'AFDXV1_cluster.xml').read_text()
 assert 'set packageName "CSG225"' in (s/'AFDXV1_pack.tcl').read_text()
 rpt=(s/'AFDXV1.map.rpt').read_text();resources={k:int(v) for k,v in re.findall(r'Total (LUTs|FFs|CLBs|Memorys|DSPs|PLLs|Pins)\s*:\s*(\d+)',util)}
 hierarchy=[]
 for line in rpt.splitlines():
  cells=[c.strip() for c in line.split(';')]
  if len(cells)>5 and cells[1].startswith('|') and any(n in cells[1] for n in ('AFDX_top','afdx_app_echo_queue:application','afdx_single_vl_tx:sender','mac_gmii_core:mac','afdx_single_vl_rx_candidate:rx_protocol','afdx_single_vl_sn_gate:sn_gate')):
   hierarchy.append({'node':cells[1],'LCs':cells[2],'FFs':int(cells[3]),'RAM_bits':int(cells[4])})
 for name in ('afdx_app_echo_queue:application','afdx_single_vl_tx:sender','mac_gmii_core:mac','afdx_single_vl_rx_candidate:rx_protocol','afdx_single_vl_sn_gate:sn_gate'):
  row=next(x for x in hierarchy if name in x['node']);assert row['FFs']>0
 assert hierarchy[0]['RAM_bits']==96224 and resources['Pins']==22 and resources['Memorys']==28
 notes={10270:'Frozen MAC gmii_txd is preassigned zero; no production change',10230:'Frozen MAC bounded width truncation',10036:'Unused frozen Parser frame_reject register',276020:'RAM bypass added to preserve read-during-write semantics',13024:'Constant output summary',13410:'Candidate tx_ready explicitly tied zero',21074:'Unused input summary',15610:'Candidate rx_ready intentionally ignored'}
 warnings=[]
 for i,line in enumerate(rpt.splitlines(),1):
  m=re.search(r'Warning \((\d+)\): (.*)',line)
  if m:code=int(m[1]);warnings.append({'index':len(warnings)+1,'line':i,'code':code,'message':m[2],'classification':notes.get(code,'REVIEW REQUIRED')})
 assert len(warnings)==25 and all(x['classification']!='REVIEW REQUIRED' for x in warnings)
 edc=p/'AFDXV1.srcs/constrs_1/new/clock_125mhz.edc';assert '-period 8.000' in edc.read_text()
 assert b'gmii_clk' in (s/'AFDXV1_clocklist.pb').read_bytes()
 result={'result':'PASS','scope':'real GUI synthesis smoke audit only','resources':resources,'warning_count':len(warnings),'warnings':warnings,'hierarchy':hierarchy,'logical_RAM_bits':96224,'RAM_bank_count':7,'core_optimized_empty':False,'diagnostic_counters_may_be_optimized':'unobserved top-internal counters; protocol/SN/data paths retained','combinational_loop_cells_reported':33,'POST_SYNTH_TIMING':'NOT VERIFIED','EQ6_NATIVE_NETLIST_EQUIVALENCE':'NOT VERIFIED','physical_IO_fit':'NOT VERIFIED','new_V1_functional_VO_test':'NOT RUN; not required by this stage smoke gate','source_integrity':'PASS','Implementation':'NOT RUN','Bitstream':'NOT RUN','synthesis_artifact_hashes':{f.name:sha(f) for f in s.iterdir() if f.is_file()}}
 (run/'synthesis_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k in ('result','resources','warning_count','hierarchy','logical_RAM_bits')},indent=2))
if __name__=='__main__':main()
