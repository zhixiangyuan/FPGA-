"""Map preserved real VO wires into read-only TB probes; never drive DUT."""
from pathlib import Path
import re,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
def main():
 vo=ROOT/'runs/eda_export_001/AFDX_top.vo';text=vo.read_text();names=set(re.findall(r'\bwire\s*(?:\[[^\]]+\]\s*)?\\(\S+)\s*;',text))
 mapping={'obs_psn':'protocol|sn_gate|psn','obs_psn_valid':'protocol|sn_gate|psn_valid~regout','obs_committed':'application|committed','obs_app_busy':'application|busy','obs_parser_busy':'protocol|rx_protocol|banks_busy','obs_mac_busy0':'protocol|tx_mac|mac|rx|bank0|busy~regout','obs_mac_busy1':'protocol|tx_mac|mac|rx|bank1|busy~regout'}
 width={'obs_psn':8,'obs_committed':2,'obs_app_busy':2,'obs_parser_busy':2}
 lines=['// Read-only connections to actual exported wires. No RTL DUT or force.']
 for dest,src in mapping.items():
  assert src in names,src;bits=f'[{width[dest]-1}:0] ' if dest in width else ''
  lines.append(f'wire {bits}{dest} = dut.\\{src} ;')
 for bank in (0,1):
  for field,w in (('lengths',11),('origins',8)):
   refs=[]
   for bit in range(w-1,-1,-1):
    name=f'application|{field}[{bank}][{bit}]~regout';assert name in names,name;refs.append('dut.\\'+name+' ')
   lines.append(f'wire [{w-1}:0] obs_{field}{bank} = '+'{'+','.join(refs)+'};')
 path=ROOT/'sim/v1_netlist_observer.vh';path.write_text('\n'.join(lines)+'\n')
 (ROOT/'runs/eda_export_001/observer_mapping.json').write_text(json.dumps({'VO_sha256':hashlib.sha256(vo.read_bytes()).hexdigest(),'mapped_wires':mapping,'application_metadata':'actual per-bit preserved lengths/origins register outputs','DUT_driven':False,'force':False,'observer_sha256':hashlib.sha256(path.read_bytes()).hexdigest()},indent=2)+'\n')
 print('V1_REAL_VO_OBSERVER_MAPPED PASS')
if __name__=='__main__':main()
