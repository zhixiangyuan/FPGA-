"""Build the bounded transport plus real atomic RAM backend, no system VO run."""
from pathlib import Path
import argparse
import json
import re
import shutil
from prepare_stage2_mgmt_elinx import ROOT,sha


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--profile',choices=('raw','615a'),default='raw');args=parser.parse_args()
    family='AFDX615' if args.profile=='615a' else 'AFDXTFTP';index=1
    top='afdx_615a_endpoint' if args.profile=='615a' else 'afdx_tftp_file_endpoint'
    while (ROOT/f'build/elinx/{family}_{index:03d}').exists():index+=1
    project=ROOT/f'build/elinx/{family}_{index:03d}'
    target=project/f'{family}.srcs/sources_1/new';target.mkdir(parents=True)
    files=[ROOT/'rtl'/n for n in ('afdx_tftp_engine.v','afdx_atomic_file_store.v')+ (('afdx_615a_error_decoder.v',) if args.profile=='615a' else ())+ (top+'.v',)]
    rows=[]
    for p in files:
        snapshot=target/p.name;shutil.copy2(p,snapshot)
        assert sha(snapshot)==sha(p)
        rows.append(dict(canonical_source=p.relative_to(ROOT).as_posix(),snapshot=snapshot.relative_to(project).as_posix(),sha256=sha(p),snapshot_sha256=sha(snapshot)))
    text=(ROOT/'elinx/AFDXV1/AFDXV1.epr').read_text().replace('AFDXV1',family).replace(
        '<Option Id="TopModule">AFDX_top</Option>',f'<Option Id="TopModule">{top}</Option>')
    file_set='\n'.join(f'            <File Path="/{r["snapshot"]}"/>' for r in rows)
    text=re.sub(r'(<FileSet Name="sources_1"[^>]*>).*?(</FileSet>)',lambda m:m[1]+'\n'+file_set+'\n        '+m[2],text,flags=re.S)
    (project/f'{family}.epr').write_text(text,encoding='utf-8')
    constraint=project/f'{family}.srcs/constrs_1/new/clock_125mhz.edc';constraint.parent.mkdir(parents=True)
    shutil.copy2(ROOT/'elinx/AFDXV1/AFDXV1.srcs/constrs_1/new/clock_125mhz.edc',constraint)
    manifest=dict(status='PREPARED_NOT_SYNTHESIZED',project=str(project/f'{family}.epr'),top=top,
        device='EQ6HL45',package='CSG225',clock_constraint_ns=8,ports=27 if args.profile=='615a' else 28,io_bits=218 if args.profile=='615a' else 183,sources=rows,
        constraint_sha256=sha(constraint),scope='configured 615A-2 / 665-2 4KiB target module' if args.profile=='615a' else '4KiB octet client/server and atomic RAM, not 615A or production top acceptance',
        POST_SYNTH_TIMING='NOT VERIFIED',EQ6_NATIVE_NETLIST_EQUIVALENCE='NOT VERIFIED',physical_IO_fit='NOT VERIFIED')
    (project/'project_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(project=manifest['project'],sources=len(rows)),indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
