"""Build a standalone, relocatable source/evidence fallback without licenses."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 target=ROOT/'delivery/V1.0';target.mkdir(parents=True,exist_ok=False)
 for n in ('rtl','sim','scripts','vendor'):shutil.copytree(ROOT/n,target/n,ignore=shutil.ignore_patterns('__pycache__'))
 for n in ('README.md','FROZEN_CORE_MANIFEST.json'):shutil.copy2(ROOT/n,target/n)
 evidence=target/'evidence';evidence.mkdir()
 for n in ('rtl_001','rtl_002','history_001','elinx_001'):
  shutil.copytree(ROOT/'runs'/n,evidence/n,ignore=shutil.ignore_patterns('work','__pycache__'))
 project=ROOT/'runs/elinx_001/AFDXV1';portable=target/'elinx/AFDXV1';portable.mkdir(parents=True)
 shutil.copy2(project/'AFDXV1.epr',portable/'AFDXV1.epr');shutil.copytree(project/'AFDXV1.srcs',portable/'AFDXV1.srcs')
 # Fresh regression references are copied as evidence, not treated as runtime dependencies.
 history=json.loads((ROOT/'runs/history_001/summary.json').read_text(encoding='utf-8-sig'))
 for label in ('b1_acceptance','b0_acceptance','stage3b2_regression'):
  src=Path(history[label]);shutil.copytree(src,evidence/('history_'+label),ignore=shutil.ignore_patterns('work'))
 b1=json.loads((Path(history['b1_acceptance'])/'summary.json').read_text(encoding='utf-8-sig'))
 for label,p in b1.get('evidence',{}).items():
  src=Path(p)
  if src.is_dir() and label not in ('stage3b2_run',):shutil.copytree(src,evidence/('history_'+label),ignore=shutil.ignore_patterns('work'),dirs_exist_ok=True)
 manifest={'version':'V1.0','profile':'TEAM_GMII_CANDIDATE','source_compile_independent':True,'upstream_source_dependency':False,'files':{str(p.relative_to(target)):sha(p) for p in target.rglob('*') if p.is_file()},'source_root':str(ROOT),'full_standard_compliance':False}
 (target/'PACKAGE_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n');print('V1_STANDALONE_PACKAGE',target)
if __name__=='__main__':main()
