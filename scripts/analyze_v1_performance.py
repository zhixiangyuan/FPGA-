"""Source-backed functional-test baseline, never a physical timing claim."""
from pathlib import Path
import csv,json,sys
ROOT=Path(__file__).resolve().parents[1]
def main(run):
 cases=json.loads((run/'golden/cases.json').read_text());byid={c['id']:c for c in cases}
 rows=list(csv.DictReader((run/'actual_tx.csv').open(newline='')));frames={}
 for row in rows:
  c=int(row['case_id']);cycle=int(row['cycle'])
  if c not in frames:frames[c]={'start':cycle,'end':cycle,'bytes':0}
  else:assert cycle==frames[c]['end']+1
  frames[c]['end']=cycle;frames[c]['bytes']+=1
 epochs={}
 for c,fr in frames.items():epochs.setdefault(byid[c]['epoch'],[]).append((c,fr))
 throughput=[];gaps=[]
 for ep,items in epochs.items():
  duration=(items[-1][1]['end']-items[0][1]['start']+1)*8
  payload=sum(byid[c]['payload_length'] for c,fr in items)
  throughput.append({'epoch':ep,'TX_frames':len(items),'payload_bytes':payload,'window_ns':duration,'observed_payload_Mbps':payload*8/duration*1000})
  gaps += [b['start']-a['start'] for (_,a),(_,b) in zip(items,items[1:])]
 latencies={};scope=''
 if (run/'input_events.csv').exists():
  inputs={int(r['case_id']):r for r in csv.DictReader((run/'input_events.csv').open(newline=''))}
  commits={int(r['case_id']):r for r in csv.DictReader((run/'app_commits.csv').open(newline=''))}
  for c,fr in frames.items():
   r=inputs[c];co=commits[c]
   latencies[c]={'RX_first_to_TX_first_ns':(fr['start']-int(r['start_cycle']))*8,'RX_last_to_TX_first_ns':(fr['start']-int(r['end_cycle']))*8,'RX_first_to_TX_last_ns':(fr['end']-int(r['start_cycle']))*8,'app_commit_to_TX_first_ns':(fr['start']-int(co['cycle']))*8}
  scope='netlist input cycles -> external TX cycles; actual bank commit cycle also measured'
 else:
  apps={}
  for r in csv.DictReader((run/'actual_app.csv').open(newline='')):
   if int(r['eop']):apps[int(r['case_id'])]=int(r['cycle'])
  for c,fr in frames.items():latencies[c]={'app_EOP_to_TX_first_ns':(fr['start']-apps[c])*8}
  scope='RTL actual app EOF -> external TX only; input RX timing not recorded in this baseline'
 limits={key:{'minimum_ns':min(r[key] for r in latencies.values()),'maximum_ns':max(r[key] for r in latencies.values())} for key in next(iter(latencies.values()))}
 result={'result':'MEASURED_FUNCTIONAL_TEST_BASELINE','run':str(run),'clock_ns':8,'continuous_TX_byte_step_cycles':1,'active_wire_byte_rate_Mbps':1000,'100_Mbps_compliance':'NOT VERIFIED','latency_scope':scope,'observed_latency_ranges':limits,'per_epoch_payload_throughput':throughput,'BAG_gaps_measured':len(gaps),'minimum_BAG_cycles':min(gaps),'maximum_BAG_cycles':max(gaps),'observed_start_gap_excess_max_ns':(max(gaps)-125000)*8,'physical_Setup_Hold':'NOT VERIFIED','worst_case_load_bound':'NOT VERIFIED; samples include pressure but no exhaustive offered-load/application-pause bound','guide_latency_and_jitter_compliance':'NOT VERIFIED; official endpoints/exact limits and 100Mbps profile remain unresolved','per_case_latency':latencies}
 (run/'performance_baseline.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('per_case_latency','per_epoch_payload_throughput')},indent=2))
if __name__=='__main__':main(Path(sys.argv[1]).resolve())
