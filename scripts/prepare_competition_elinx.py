"""Snapshot the application/dual-network candidate for native EQ6 synthesis."""
from pathlib import Path
import json, re, shutil
from run_competition import ROOT, sources, sha

def main():
    family='AFDXSUB';i=1
    while (ROOT/f'build/elinx/{family}_{i:03d}').exists():i+=1
    project=ROOT/f'build/elinx/{family}_{i:03d}'
    target=project/f'{family}.srcs/sources_1/new';target.mkdir(parents=True)
    frozen=json.loads((ROOT/'FROZEN_CORE_MANIFEST.json').read_text())
    for r in frozen:assert sha(ROOT/'vendor/frozen'/Path(r['snapshot']).name)==r['sha256']
    rows=[]
    for p in sources():
        out=target/p.name;shutil.copy2(p,out)
        rows.append(dict(canonical_source=p.relative_to(ROOT).as_posix(),snapshot=out.relative_to(project).as_posix(),
                         sha256=sha(p),snapshot_sha256=sha(out)))
    template=(ROOT/'elinx/AFDXV1/AFDXV1.epr').read_text().replace('AFDXV1',family)
    template=template.replace('EQ6HL45','EQ6HL130').replace('CSG225','CSG484_H')
    listing='\n'.join(f'            <File Path="/{r["snapshot"]}"/>' for r in rows)
    template=re.sub(r'(<FileSet Name="sources_1"[^>]*>).*?(</FileSet>)',lambda m:m[1]+'\n'+listing+'\n        '+m[2],template,flags=re.S)
    (project/f'{family}.epr').write_text(template,encoding='utf-8')
    constraint=project/f'{family}.srcs/constrs_1/new/clock_125mhz.edc';constraint.parent.mkdir(parents=True)
    shutil.copy2(ROOT/'elinx/AFDXV1/AFDXV1.srcs/constrs_1/new/clock_125mhz.edc',constraint)
    manifest=dict(status='PREPARED_NOT_SYNTHESIZED',project=str(project/f'{family}.epr'),top='AFDX_top',
                  device='EQ6HL130',package='CSG484_H',clock_constraint_ns=8,sources=rows,
                  constraint_sha256=sha(constraint),scope='application business dual-network candidate, 128 TX / 4096 RX',
                  management='SNMP/SNTP/RTC/615A connected; new wrapper full 615A sessions pending',
                  POST_SYNTH_TIMING='NOT VERIFIED',EQ6_NATIVE_NETLIST_EQUIVALENCE='NOT VERIFIED')
    (project/'project_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(project)
    return 0

if __name__=='__main__':raise SystemExit(main())
