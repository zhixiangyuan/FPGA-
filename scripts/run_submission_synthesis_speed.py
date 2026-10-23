"""Synthesise the production AFDX_top wrapper with the verified SPEED target.

The eLinx GUI rewrites AFDXSUB.qsf on every run and falls back to BALANCED,
which is the candidate that misses the 8 ns setup estimate. This runner builds
a fresh numbered project from the canonical sources, pins
STRATIX_OPTIMIZATION_TECHNIQUE to SPEED, runs Analysis & Synthesis headlessly
and prints the resource/warning summary from the generated reports.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import prepare_submission_elinx as prepare  # noqa: E402

FAMILY = 'AFDXSUB'


def projects():
    return sorted((ROOT / 'build/elinx').glob(f'{FAMILY}_[0-9][0-9][0-9]'))


def find_map_tool():
    candidates = [os.environ.get('ELINX_MAP_EXE'),
                  r'D:\elinx\eLinx3.0\bin\Passkey\bin\quartus_map.exe',
                  r'D:\FPGA\eLinx3.0\bin\Passkey\bin\quartus_map.exe']
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise SystemExit('quartus_map.exe not found; set ELINX_MAP_EXE')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--optimization-technique', choices=('SPEED', 'BALANCED'), default='SPEED')
    args = parser.parse_args()
    previous = projects()
    if not previous:
        raise SystemExit('no AFDXSUB project to borrow settings from; run the GUI once first')
    prepare.main()
    project = projects()[-1]
    template = previous[-1] / f'{FAMILY}.qsf'
    text = template.read_text()
    text = text.replace(previous[-1].as_posix(), project.as_posix())
    text = re.sub(r'STRATIX_OPTIMIZATION_TECHNIQUE \w+',
                  'STRATIX_OPTIMIZATION_TECHNIQUE ' + args.optimization_technique, text)
    (project / f'{FAMILY}.qsf').write_text(text)
    (project / f'{FAMILY}.qpf').write_text('PROJECT_REVISION = "' + FAMILY + '"\n')
    tool = find_map_tool()
    command = [str(tool), '--read_settings_files=on', '--write_settings_files=off', FAMILY]
    code = subprocess.run(command, cwd=project).returncode
    report = project / f'{FAMILY}.runs/synth_1' / f'{FAMILY}.map.rpt'
    body = report.read_text(errors='replace') if report.exists() else ''
    passed = code == 0 and 'Analysis & Synthesis was successful' in body and 'Error (' not in body
    classes = {}
    for match in re.finditer(r'Warning \((\d+)\)', body):
        classes[match.group(1)] = classes.get(match.group(1), 0) + 1
    summary = {}
    path = project / f'{FAMILY}.runs/synth_1' / f'{FAMILY}.map.summary'
    if path.exists():
        for line in path.read_text().splitlines():
            if ':' in line and line.split(':')[0].strip():
                key, value = line.split(':', 1)
                summary[key.strip()] = value.strip()
    print(json.dumps({'result': 'PASS' if passed else 'FAIL', 'project': str(project),
                      'optimization_technique': args.optimization_technique,
                      'synthesis': summary, 'warning_classes': classes}, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())

