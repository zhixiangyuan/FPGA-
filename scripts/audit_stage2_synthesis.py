"""Audit actual eLinx Stage2 synthesis artifacts without running any tool flow."""
from pathlib import Path
import argparse,json,hashlib,re
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--project-dir',type=Path,required=True)
 project=parser.parse_args().project_dir.resolve();out=project/'AFDXS2.runs/synth_1'
 manifest=json.loads((project/'project_manifest.json').read_text())
 for row in manifest['sources']:assert sha(project/row['snapshot'])==row['sha256']==sha(ROOT/row['canonical_source'])
 util=(out/'AFDXS2_utilization_synth.rpt').read_text();assert 'Synthesis Status : Successful' in util
 assert 'Top-level Entity Name : afdx_stage2_top' in util
 resources={k:int(v) for k,v in re.findall(r'Total (LUTs|FFs|CLBs|Memorys|DSPs|PLLs|Pins)\s*:\s*(\d+)',util)}
 assert resources['Pins']==22 and resources['LUTs']<42560 and resources['FFs']<42560 and resources['Memorys']<=392
 assert 'device_name="EQ6HL45"' in (out/'AFDXS2_cluster.xml').read_text()
 assert 'set packageName "CSG225"' in (out/'AFDXS2_pack.tcl').read_text()
 assert '-period 8.000' in (project/'AFDXS2.srcs/constrs_1/new/clock_125mhz.edc').read_text()
 assert 'read_sdc' in (out/'AFDXS2.run.psf').read_text() and b'gmii_clk' in (out/'AFDXS2_clocklist.pb').read_bytes()
 report=(out/'AFDXS2.map.rpt').read_text();assert 'Analysis & Synthesis was successful' in report and 'Error (' not in report
 hierarchy=[]
 names=('afdx_multi_vl_echo_queue:application','afdx_multi_vl_tx:sender','mac_gmii_core:mac','afdx_multi_vl_rx_parser:parser','afdx_multi_vl_sn_gate:gate')
 for line in report.splitlines():
  cells=[x.strip() for x in line.split(';')]
  if len(cells)>5 and cells[1].strip('|') in names:
   hierarchy.append({'module':cells[1].strip('|'),'LCs':cells[2],'FFs':int(cells[3]),'RAM_bits':int(cells[4])})
 assert {r['module'] for r in hierarchy}==set(names) and all(r['FFs']>0 for r in hierarchy)
 assert next(r['RAM_bits'] for r in hierarchy if r['module']==names[0])==16*2*1471*8
 warnings=[]
 classifications={10230:'Bounded truncation: bank indices <=31, round-robin <=15; frozen MAC widths retain approved bounds',
  10270:'Frozen MAC case default is covered by preceding zero assignment; original source retained',
  10036:'Unused diagnostic pulse/wire; not part of accepted data path',
  276020:'RAM pass-through added for read-during-write; real VO validation still required',
  276027:'Application RAM uses two ports tied to the same clk; collision semantics require ownership/pressure and VO checks',
  13024:'Constant output summary',13410:'tx_ready=0 allowed by official FAQ C62',
  21074:'Unused input summary',15610:'rx_ready ignored as allowed by official FAQ C62'}
 for number,line in enumerate(report.splitlines(),1):
  match=re.search(r'Warning \((\d+)\): (.*)',line)
  if match:warnings.append({'line':number,'code':int(match[1]),'message':match[2],'classification':classifications.get(int(match[1]),'REVIEW REQUIRED')})
 assert len(warnings)==29 and all(w['classification']!='REVIEW REQUIRED' for w in warnings)
 loops=int(re.search(r'Number of logic cells representing combinational loops\s*;\s*(\d+)',report)[1])
 result={'result':'PASS','scope':'actual EQ6HL45/CSG225 eLinx synthesis/resource and source audit; not timing/function proof',
  'resources':resources,'hierarchy':hierarchy,'warnings':warnings,'warning_count':len(warnings),'combinational_loop_cells':loops,
  'application_RAM_collision_semantics':'NOT VERIFIED by synthesis alone','core_optimized_empty':False,
  'diagnostic_counters':'may be optimized; never substitute zero for observed counters',
  'POST_SYNTH_TIMING':'NOT VERIFIED','EQ6_NATIVE_NETLIST_EQUIVALENCE':'NOT VERIFIED','physical_IO_fit':'NOT VERIFIED',
  'Implementation':'NOT RUN','Bitstream':'NOT RUN','source_integrity':'PASS',
  'synthesis_artifact_hashes':{p.name:sha(p) for p in out.iterdir() if p.is_file()}}
 (project/'synthesis_audit.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:v for k,v in result.items() if k in ('result','scope','resources','warning_count','combinational_loop_cells','hierarchy')},indent=2))
 return 0
if __name__=='__main__':raise SystemExit(main())
