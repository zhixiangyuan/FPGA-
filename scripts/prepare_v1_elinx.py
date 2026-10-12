"""Prepare one independent synthesis smoke project, never run fit/bitstream."""
from pathlib import Path
import json,hashlib,shutil,re
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 assert json.loads((ROOT/'runs/rtl_002/verification.json').read_text())['result']=='PASS'
 run=ROOT/'runs/elinx_001';prj=run/'AFDXV1';name='AFDXV1';src=prj/f'{name}.srcs/sources_1/new';con=prj/f'{name}.srcs/constrs_1/new';src.mkdir(parents=True);con.mkdir(parents=True)
 files=[*sorted((ROOT/'vendor/frozen').glob('*.v')),*sorted((ROOT/'rtl').glob('*.v'))]
 rows=[]
 for p in files:q=src/p.name;shutil.copy2(p,q);rows.append({'original':str(p),'snapshot':str(q),'sha256':sha(p),'snapshot_sha256':sha(q)})
 constraint=con/'clock_125mhz.edc';constraint.write_text('create_clock -name gmii_clk -period 8.000 -waveform {0.000 4.000} [get_ports clk]\n')
 template=ROOT.parent/'stage5B2_rx_arch_20261011/runs/elinx_002/AFDXB2/AFDXB2.epr'
 # Start from the proven EPR schema; replace sources and preserve synthesis-only flow.
 text=template.read_text().replace('AFDXB2','AFDXV1').replace('afdx_b2_synth_wrap','AFDX_top')
 text=re.sub(r'<FileSet Name="sources_1".*?</FileSet>','<FileSet Name="sources_1" Type="DesignSrcs" RelSrcDir="$PSRCDIR/sources_1">\n'+ '\n'.join(f'<File Path="/AFDXV1.srcs/sources_1/new/{p.name}"/>' for p in files)+'\n</FileSet>',text,flags=re.S)
 (prj/'AFDXV1.epr').write_text(text)
 ports=re.findall(r'\b(input|output)\s+wire\s*(?:\[(\d+):(\d+)\])?\s+(\w+)',(ROOT/'rtl/AFDX_top.v').read_text().split(');')[0]);budget=sum(abs(int(a)-int(b))+1 if a else 1 for _,a,b,n in ports);assert budget==22 and len(ports)==8
 manifest={'status':'PREPARED_NOT_SYNTHESIZED','project':str(prj/'AFDXV1.epr'),'top':'AFDX_top','target':'EQ6HL45/CSG225','ports':22,'sources':rows,'constraint_sha256':sha(constraint),'logical_memory_bits':72688+23536,'application_bank_count':2,'production_modified':False,'Implementation':'NOT RUN','POST_SYNTH_TIMING':'NOT VERIFIED','physical_fit':'NOT VERIFIED'}
 (run/'project_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 handoff=f'''# V1.0 综合冒烟人工接力（一次）

工程：`{prj / 'AFDXV1.epr'}`。

1. 在eLinx中打开此独立工程，确认Top=AFDX_top，Device=EQ6HL45，Package=CSG225。
2. Sources应有16个Verilog文件；Constraints选择clock_125mhz.edc（8.000ns）。
3. 只执行 **Run Synthesis**，等待Synthesis Complete。
4. 回报Errors/Warnings及LUT、FF、Memory、IO；保留GUI产物，Codex随后读取真实map/EDI/utilization报告审计。

不执行Implementation、Bitstream或下载；不打开冻结生产工程来替换源码。当前RTL八端口22位仅是声明统计，不是物理fit PASS。此前eLinx打开工程对话框自动化焦点不可读，因此本轮采用既定人工接力，不重复自动点击。
'''
 (run/'GUI综合冒烟接力.md').write_text(handoff,encoding='utf-8');print('V1_SYNTHESIS_PREPARED',prj/'AFDXV1.epr')
if __name__=='__main__':main()
