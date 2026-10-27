"""Run the nine-scenario submission testbench on the post-synthesis netlist.

The RTL run (run_submission.py) proves functional intent. This runner compiles
the EDA netlist (`quartus_eda --simulation`) together with the same Golden
stimulus and checks the identical wire-level expectations, so the accepted
behaviour is demonstrated after synthesis as well.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from run_stage2_mgmt import MS, sha  # noqa: E402
from modelsim_support import prepare_ini  # noqa: E402
import run_submission  # noqa: E402

LIBS = ('altera_primitives.v', '220model.v', 'altera_mf.v', 'stratix_atoms.v')
LIB_DIR = Path(r'D:\elinx\eLinx3.0\Simulation\elinx_lib')


def newest_netlist():
    found = sorted((ROOT / 'build/elinx').glob('AFDXSUB_[0-9][0-9][0-9]/simulation/modelsim/AFDXSUB.vo'))
    return found[-1] if found else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--netlist', type=Path)
    parser.add_argument('--timeout', type=int, default=5400)
    args = parser.parse_args()
    netlist = args.netlist or newest_netlist()
    if netlist is None or not netlist.is_file():
        raise SystemExit('no AFDXSUB.vo found; run quartus_eda --simulation --functional first')
    index = 1
    while (ROOT / f'build/logs/submission_vo_{index:03d}').exists():
        index += 1
    run = ROOT / f'build/logs/submission_vo_{index:03d}'
    run.mkdir(parents=True)
    shutil.copy2(netlist, run / 'AFDX_top.vo')
    for name in LIBS:
        shutil.copy2(LIB_DIR / name, run / name)
    shutil.copy2(ROOT / 'sim/tb_submission_vo.sv', run / 'tb_submission_vo.sv')
    expected = run_submission.generate(run / 'golden')
    prepare_ini(run, MS)
    commands = ['onerror {quit -code 2 -force}', 'vlib work']
    commands += [f'vlog {name}' for name in LIBS]
    commands += ['vlog AFDX_top.vo', 'vlog -sv tb_submission_vo.sv',
                 'vopt -O5 work.tb_submission_vo -o submission_vo_opt',
                 'vsim -t 1ps work.submission_vo_opt', 'run -all', 'quit -code 0 -force']
    (run / 'run.do').write_text('\n'.join(commands) + '\n')
    env = os.environ.copy()
    env.setdefault('MGLS_LICENSE_FILE', str(MS.parent / 'LICENSE.TXT'))
    summary = dict(result='RUNNING', backend='POST_SYNTHESIS_NETLIST', netlist=str(netlist),
                   netlist_sha256=sha(netlist), started_utc=datetime.now(timezone.utc).isoformat(),
                   golden={p.name: sha(p) for p in (run / 'golden').iterdir()})
    proof = run / 'summary.json'
    proof.write_text(json.dumps(summary, indent=2) + '\n')
    with (run / 'console.log').open('wb') as log:
        process = subprocess.Popen([str(MS / 'vsim.exe'), '-batch', '-modelsimini', 'modelsim.ini',
                                    '-l', 'transcript.log', '-do', 'do run.do'], cwd=run, env=env,
                                   stdout=log, stderr=subprocess.STDOUT)
        print(f'SUBMISSION_VO_RUN {run} PID {process.pid}', flush=True)
        code = process.wait(timeout=args.timeout)
    transcript = (run / 'transcript.log').read_text(errors='replace')
    passed = code == 0 and 'SUBMISSION_VO_PASS' in transcript and '** Error' not in transcript
    error = None
    evidence = {}
    if passed:
        try:
            evidence = run_submission.verify(run, expected)
            evidence['VO'] = 'PASS'
        except (AssertionError, KeyError, ValueError) as exc:
            error = str(exc)
            passed = False
    summary.update(result='PASS' if passed else 'FAIL', exit_code=code, error=error, evidence=evidence,
                   completed_utc=datetime.now(timezone.utc).isoformat())
    proof.write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())

