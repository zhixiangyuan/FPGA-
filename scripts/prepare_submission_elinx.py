"""Prepare the eight-port AFDX_top target with explicit canonical sources."""
import json
import re
import shutil
from pathlib import Path

from submission_sources import ROOT, sources
from prepare_stage2_mgmt_elinx import sha
from check_top_drivers import module_signatures, strip_comments


def main():
    family='AFDXSUB';index=1
    while (ROOT/f'build/elinx/{family}_{index:03d}').exists():index+=1
    project=ROOT/f'build/elinx/{family}_{index:03d}'
    target=project/f'{family}.srcs/sources_1/new';target.mkdir(parents=True)
    files=sources()
    assert ROOT/'rtl/AFDX_top.v' not in files
    frozen=json.loads((ROOT/'FROZEN_CORE_MANIFEST.json').read_text())
    for row in frozen:assert sha(ROOT/'vendor/frozen'/Path(row['snapshot']).name)==row['sha256']
    rows=[]
    for p in files:
        snapshot=target/p.name;shutil.copy2(p,snapshot)
        assert sha(snapshot)==sha(p)
        rows.append(dict(canonical_source=p.relative_to(ROOT).as_posix(),
                         snapshot=snapshot.relative_to(project).as_posix(),sha256=sha(p),snapshot_sha256=sha(snapshot)))
    template=(ROOT/'elinx/AFDXV1/AFDXV1.epr').read_text().replace('AFDXV1',family)
    file_set='\n'.join(f'            <File Path="/{r["snapshot"]}"/>' for r in rows)
    template=re.sub(r'(<FileSet Name="sources_1"[^>]*>).*?(</FileSet>)',
                    lambda m:m[1]+'\n'+file_set+'\n        '+m[2],template,flags=re.S)
    (project/f'{family}.epr').write_text(template,encoding='utf-8')
    constraint=project/f'{family}.srcs/constrs_1/new/clock_125mhz.edc';constraint.parent.mkdir(parents=True)
    shutil.copy2(ROOT/'elinx/AFDXV1/AFDXV1.srcs/constrs_1/new/clock_125mhz.edc',constraint)
    assert '-period 8.000' in constraint.read_text()
    ports=module_signatures(strip_comments((ROOT/'rtl/submission/AFDX_top.v').read_text()))['AFDX_top']
    assert ports==dict(clk='input',reset='input',tx_data='output',rx_data='input',
                       tx_valid='output',rx_valid='input',tx_ready='output',rx_ready='input'),ports
    manifest=dict(status='PREPARED_NOT_SYNTHESIZED',project=str(project/f'{family}.epr'),top='AFDX_top',
        device='EQ6HL45',package='CSG225',clock_constraint_ns=8,ports=8,io_bits=22,
        sources=rows,constraint_sha256=sha(constraint),
        scope='production eight-port 16-VL business plus SNMP and autonomous SNTP; 615A not integrated',
        POST_SYNTH_TIMING='NOT VERIFIED',EQ6_NATIVE_NETLIST_EQUIVALENCE='NOT VERIFIED',physical_IO_fit='NOT VERIFIED')
    (project/'project_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(project=manifest['project'],sources=len(rows),ports=8,io_bits=22),indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
