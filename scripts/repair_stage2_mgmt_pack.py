"""Retry management synthesis packing after the PSF constraint-path error."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / 'build/elinx/AFDXS2M_002'
OUT = PROJECT / 'AFDXS2M.runs/synth_1'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    proof_path = PROJECT / 'database_mapping_provenance.json'
    runner_path = PROJECT / 'synthesis_runner.json'
    proof = json.loads(proof_path.read_text())
    runner = json.loads(runner_path.read_text())
    failed_log = PROJECT / 'database_pack.log'
    assert proof['result'] == 'FAIL' and proof['pack_exit_code'] == 0
    assert runner['exit_code'] == 0 and runner['backend_exit_code'] == 1
    assert 'AFDXS2.srcs/constrs_1/new/clock_125mhz.edc' in failed_log.read_text()
    assert sha(OUT / 'AFDXS2M_database.vqm') == proof['vqm_sha256']
    assert sha(OUT / 'AFDXS2M.map.rpt') == proof['source_map_report_sha256']
    assert sha(OUT / 'AFDXS2M_database_pack.tcl') == proof['pack_script_sha256']
    for source in proof['artifacts']:
        path = OUT / source
        assert sha(path) == proof['artifacts'][source], source

    archived = PROJECT / 'database_pack_initial_failure.log'
    archived_proof = PROJECT / 'database_mapping_initial_failure.json'
    assert not archived.exists() and not archived_proof.exists()
    shutil.copy2(failed_log, archived)
    shutil.copy2(proof_path, archived_proof)
    psf = OUT / 'AFDXS2M.run.psf'
    old = psf.read_text()
    assert 'AFDXS2.srcs/' in old
    new = old.replace('AFDXS2.srcs/', 'AFDXS2M.srcs/')
    assert 'AFDXS2.srcs/' not in new
    assert (PROJECT / 'AFDXS2M.srcs/constrs_1/new/clock_125mhz.edc').exists()
    psf.write_text(new)

    command = proof['pack_command']
    assert command[1:] == ['-f', str(OUT / 'AFDXS2M_database_pack.tcl')]
    with failed_log.open('wb') as log:
        code = subprocess.run(command, cwd=Path(command[0]).parent,
                              stdout=log, stderr=subprocess.STDOUT, timeout=600).returncode
    report = OUT / 'AFDXS2M_utilization_synth.rpt'
    passed = (code == 0 and report.exists() and
              'Synthesis Status : Successful' in report.read_text(errors='replace') and
              (OUT / 'AFDXS2M_netlist.pb').exists() and
              (OUT / 'AFDXS2M_eHiChip6.ecp').exists())
    repair = {'reason': 'PSF referenced AFDXS2.srcs instead of AFDXS2M.srcs',
              'initial_log_sha256': sha(archived),
              'initial_provenance_sha256': sha(archived_proof),
              'corrected_psf_sha256': sha(psf),
              'retry_log_sha256': sha(failed_log),
              'retry_exit_code': code,
              'completed_utc': datetime.now(timezone.utc).isoformat()}
    proof.update(result='PASS' if passed else 'FAIL', pack_exit_code=code,
                 repair=repair, completed_utc=repair['completed_utc'],
                 artifacts={p.name: sha(p) for p in OUT.iterdir() if p.is_file()})
    proof_path.write_text(json.dumps(proof, indent=2) + '\n')
    runner.update(result='PASS' if passed else 'FAIL', backend_exit_code=code,
                  repair=repair, completed_utc=repair['completed_utc'],
                  eHiWay_backend_artifacts_present=(OUT / 'AFDXS2M_netlist.pb').exists(),
                  artifacts={p.name: sha(p) for p in OUT.iterdir() if p.is_file()})
    runner_path.write_text(json.dumps(runner, indent=2) + '\n')
    print(json.dumps({'result': proof['result'], 'repair': repair}, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
