"""Prepare a real independent synthesis build for the management-service top.

The business top keeps its own generator and project family; this one builds the
top that carries both service VLs so the SNMP, SNTP and RTC logic is covered by a
real vendor frontend run as well.
"""
from pathlib import Path
import hashlib,json,re,shutil
ROOT=Path(__file__).resolve().parents[1]
MGR_RTL=('afdx_multi_vl_rx_parser.v','afdx_multi_vl_sn_gate.v','afdx_multi_vl_echo_queue.v','afdx_multi_vl_tx.v',
 'afdx_snmp_agent.v','afdx_service_message_fifo.v','afdx_service_tx_arbiter.v','afdx_management_rx_demux.v',
 'afdx_sntp_client.v','afdx_rtc_timebase.v','afdx_stage2_mgmt_top.v')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 parent=ROOT/'build/elinx';i=1
 while (parent/f'AFDXS2M_{i:03d}').exists():i+=1
 project=parent/f'AFDXS2M_{i:03d}';project.mkdir(parents=True)
 source_dir=project/'AFDXS2M.srcs/sources_1/new';source_dir.mkdir(parents=True)
 sources=sorted((ROOT/'vendor/frozen').glob('*.v'))+[ROOT/'rtl'/n for n in MGR_RTL]
 frozen=json.loads((ROOT/'FROZEN_CORE_MANIFEST.json').read_text())
 for row in frozen:assert sha(ROOT/'vendor/frozen'/Path(row['snapshot']).name)==row['sha256']
 rows=[]
 for source in sources:
  target=source_dir/source.name;shutil.copy2(source,target)
  assert sha(source)==sha(target)
  rows.append({'canonical_source':source.relative_to(ROOT).as_posix(),'snapshot':target.relative_to(project).as_posix(),'sha256':sha(source),'snapshot_sha256':sha(target)})
 template=(ROOT/'elinx/AFDXV1/AFDXV1.epr').read_text()
 text=template.replace('AFDXV1','AFDXS2M').replace('<Option Id="TopModule">AFDX_top</Option>','<Option Id="TopModule">afdx_stage2_mgmt_top</Option>')
 file_set='\n'.join(f'            <File Path="/AFDXS2M.srcs/sources_1/new/{s.name}"/>' for s in sources)
 text=re.sub(r'(<FileSet Name="sources_1"[^>]*>).*?(</FileSet>)',lambda m:m[1]+'\n'+file_set+'\n        '+m[2],text,flags=re.S)
 (project/'AFDXS2M.epr').write_text(text,encoding='utf-8')
 constraint=project/'AFDXS2M.srcs/constrs_1/new/clock_125mhz.edc';constraint.parent.mkdir(parents=True)
 shutil.copy2(ROOT/'elinx/AFDXV1/AFDXV1.srcs/constrs_1/new/clock_125mhz.edc',constraint)
 assert '-period 8.000' in constraint.read_text()
 header=(ROOT/'rtl/afdx_stage2_mgmt_top.v').read_text().split(');',1)[0]
 for port in ('clk','reset','rx_data','rx_valid','rx_ready','tx_data','tx_valid','tx_ready',
              'uptime_override','uptime_override_en','sntp_request_start'):
  assert port in header,port
 manifest={'status':'PREPARED_NOT_SYNTHESIZED','project':str(project/'AFDXS2M.epr'),'top':'afdx_stage2_mgmt_top',
           'device':'EQ6HL45','package':'CSG225','clock_constraint_ns':8,'ports':11,'io_bits':56,
           'sources':rows,'constraint_sha256':sha(constraint),
           'scope':'management services: SNMP on 0x1244 and SNTP/RTC on 0x1245 sharing the 16-VL business echo path',
           'POST_SYNTH_TIMING':'NOT VERIFIED','EQ6_NATIVE_NETLIST_EQUIVALENCE':'NOT VERIFIED','physical_IO_fit':'NOT VERIFIED'}
 (project/'project_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps({'project':str(project/'AFDXS2M.epr'),'sources':len(rows),'io_bits':56,'status':manifest['status']},indent=2))
 return 0
if __name__=='__main__':raise SystemExit(main())
