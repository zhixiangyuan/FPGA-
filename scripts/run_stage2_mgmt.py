"""Management-service system run: business echo plus SNMP over the real MAC."""
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_stage2_mgmt_golden import generate

ROOT = Path(__file__).resolve().parents[1]
MS = Path(os.environ.get('MODELSIM_BIN', r'D:\FPGA\Modlesim20.4\ModelSim20.4\win64'))
RTL = ('afdx_multi_vl_rx_parser.v', 'afdx_multi_vl_sn_gate.v', 'afdx_multi_vl_echo_queue.v', 'afdx_multi_vl_tx.v',
       'afdx_snmp_agent.v', 'afdx_service_message_fifo.v', 'afdx_service_tx_arbiter.v', 'afdx_management_rx_demux.v',
       'afdx_stage2_mgmt_top.v')
BUSINESS_VL = 0x1234
MGMT_VL = 0x1244


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parent = ROOT / 'build/logs'
    index = 1
    while (parent / f'mgmt_{index:03d}').exists():
        index += 1
    run = parent / f'mgmt_{index:03d}'
    run.mkdir(parents=True)
    sources = sorted((ROOT / 'vendor/frozen').glob('*.v')) + [ROOT / 'rtl' / n for n in RTL] + [ROOT / 'sim/tb_stage2_mgmt.sv']
    scripts = [Path(__file__), ROOT / 'scripts/generate_stage2_mgmt_golden.py',
               ROOT / 'scripts/generate_snmp_golden.py', ROOT / 'scripts/frozen_frame_reference.py']
    for path in sources + scripts:
        shutil.copy2(path, run / path.name)
    manifest = generate(run / 'golden')
    shutil.copy2(MS.parent / 'modelsim.ini', run / 'modelsim.ini')
    os.chmod(run / 'modelsim.ini', 0o666)
    commands = ['onerror {quit -code 2 -force}', 'vlib work', 'vmap work work']
    commands += [f'vlog {"-sv " if path.suffix == ".sv" else ""}+incdir+{run.as_posix()} {path.name}' for path in sources]
    commands += ['vopt -O5 +acc=nr+tb_stage2_mgmt work.tb_stage2_mgmt -o mgmt_optimized',
                 'vsim -t 1ps -wlf waves.wlf work.mgmt_optimized',
                 'log /tb_stage2_mgmt/reset /tb_stage2_mgmt/gmii_rxd /tb_stage2_mgmt/gmii_rx_dv /tb_stage2_mgmt/tx_data /tb_stage2_mgmt/tx_valid',
                 'run -all', 'quit -code 0 -force']
    (run / 'run.do').write_text('\n'.join(commands) + '\n', encoding='ascii')
    env = os.environ.copy()
    env.setdefault('MGLS_LICENSE_FILE', str(MS.parent / 'LICENSE.TXT'))
    command = [str(MS / 'vsim.exe'), '-batch', '-modelsimini', 'modelsim.ini', '-l', 'transcript.log', '-do', 'do run.do']
    summary = {'result': 'RUNNING', 'started_utc': datetime.now(timezone.utc).isoformat(), 'golden': manifest,
               'scope': 'management-service system: 16-VL business echo plus SNMPv1 over the shared real MAC',
               'inputs': {str(p.relative_to(ROOT)): sha(p) for p in sources + scripts}, 'command': command}
    with (run / 'console.log').open('wb') as log:
        process = subprocess.Popen(command, cwd=run, env=env, stdout=log, stderr=subprocess.STDOUT)
        summary['modelsim_pid'] = process.pid
        (run / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
        print(f'MGMT_SERVICE_RUN {run} PID {process.pid}', flush=True)
        code = process.wait(timeout=7200)
    text = (run / 'transcript.log').read_text(errors='replace')
    error = None
    checked = 0
    passed = code == 0 and 'MGMT_SERVICE_RUN' in text and 'Errors: 0' in text and '** Fatal' not in text and '** Error' not in text
    evidence = {}
    if passed:
        try:
            cases = json.loads((run / 'golden/cases.json').read_text(encoding='utf-8'))
            expected_wire = (run / 'golden/expected_tx_wire.mem').read_text().split()
            expected_wire = bytes(int(byte, 16) for byte in expected_wire)
            expected = [(case, expected_wire[case['tx_offset']:case['tx_offset'] + case['tx_length']])
                        for case in cases if case['expect_tx']]
            service_cases = [c for c in cases if c['kind'] == 'snmp']
            filtered = [c for c in cases if c['kind'] in ('snmp', 'unknown_port')]
            events = list(csv.DictReader((run / 'tx_events.csv').open(newline='')))
            inputs = {int(row['frame']): row for row in csv.DictReader((run / 'rx_events.csv').open(newline=''))}
            actual = bytes(int(byte, 16) for byte in (run / 'actual_tx.mem').read_text().split())
            assert len(events) == len(expected), f'transmitted {len(events)} frames, expected {len(expected)}'
            offset = 0
            gaps = defaultdict(list)
            last_start = {}
            latencies = []
            for event, (case, wire) in zip(events, expected):
                size = int(event['bytes'])
                frame = actual[offset:offset + size]
                offset += size
                assert frame == wire, f'wire mismatch for case {case["name"]}'
                assert int(event['end_cycle']) - int(event['start_cycle']) + 1 == size
                # Each recorded frame is the full GMII wire frame: eight bytes
                # of preamble and SFD, then DA, SA and the type field. The VLID
                # is the low half of the 48-bit AFDX DA.
                vlid = int.from_bytes(frame[12:14], 'big')
                assert vlid == (BUSINESS_VL if case['kind'] == 'business' else MGMT_VL), \
                    f'wrong VLID on the wire for case {case["name"]}: {vlid:04x}'
                start = int(event['start_cycle'])
                if vlid in last_start:
                    gaps[vlid].append(start - last_start[vlid])
                last_start[vlid] = start
                source = inputs[case['id']]
                latencies.append({'case': case['name'], 'kind': case['kind'],
                                  'gmii_in_to_out_ns': (start - int(source['start_cycle'])) * 8})
                checked += 1
            assert offset == len(actual), 'unexplained trailing transmit bytes'
            assert min(gaps[BUSINESS_VL]) >= 125000, f'business BAG {min(gaps[BUSINESS_VL])}'
            assert min(gaps[MGMT_VL]) >= 125000, f'management BAG {min(gaps[MGMT_VL])}'
            counters = {row['key']: int(row['value']) for row in csv.DictReader((run / 'counters.csv').open(newline=''))}
            service_frames = [c for c in cases if c['expect_tx'] and c['kind'] != 'business']
            assert counters['tx_frames'] == len(expected)
            assert counters['demux_routed'] == len(service_cases), counters['demux_routed']
            assert counters['demux_dropped'] == 1 and counters['demux_last_dropped_port'] == 9999
            assert counters['mgmt_gate_rejected'] == 1
            assert counters['mgmt_gate_delivered'] == len(filtered)
            assert counters['arbiter_service_sent'] == len(service_frames)
            assert counters['fifo_captured'] == counters['fifo_sent'] == len(service_frames)
            assert counters['fifo_overflow'] == 0 and counters['snmp_trap'] == 0
            assert counters['business_gate_delivered'] == 2 and counters['application_sent'] == 2
            assert counters['application_error'] == 0 and counters['arbiter_service_error'] == 0
            # Both receive parsers observe every wire frame on the shared MAC,
            # so each one also counts the frames that belong to the other path.
            business_cases = [c for c in cases if c['kind'] == 'business']
            wrong_peer_cases = [c for c in cases if c['kind'] == 'bad_peer']
            assert counters['business_parser_accepted'] == len(business_cases), counters['business_parser_accepted']
            assert counters['business_parser_rejected'] == len(cases) - len(business_cases), \
                counters['business_parser_rejected']
            assert counters['mgmt_parser_rejected'] == len(business_cases) + len(wrong_peer_cases), \
                counters['mgmt_parser_rejected']
            evidence = {
                'frames_compared': checked, 'service_responses': len(service_frames),
                'snmp_ber_cases_over_the_link': len(service_cases),
                'negative_cases': {'unknown_port_drained': counters['demux_dropped'],
                                   'parser_rejected_peer': counters['mgmt_parser_rejected'],
                                   'gate_rejected_duplicate_sn': counters['mgmt_gate_rejected']},
                'counters': counters,
                'bag_cycles': {hex(BUSINESS_VL): {'min': min(gaps[BUSINESS_VL]), 'max': max(gaps[BUSINESS_VL])},
                               hex(MGMT_VL): {'min': min(gaps[MGMT_VL]), 'max': max(gaps[MGMT_VL])}},
                'gmii_in_to_out_ns': {'min': min(item['gmii_in_to_out_ns'] for item in latencies),
                                      'max': max(item['gmii_in_to_out_ns'] for item in latencies)},
                'snmp_uptime_ticks_final': counters['uptime_ticks'],
            }
            (run / 'latencies.json').write_text(json.dumps(latencies, indent=2) + '\n', encoding='utf-8')
        except (AssertionError, IndexError, KeyError) as exc:
            passed = False
            error = f'independent comparison failed: {exc}'
    summary.update(result='PASS' if passed else 'FAIL', exit_code=code, frames_compared=checked, error=error,
                   evidence=evidence, completed_utc=datetime.now(timezone.utc).isoformat(),
                   artifacts={p.name: sha(p) for p in run.iterdir() if p.is_file() and p.name != 'summary.json'})
    (run / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(text[-1200:])
    print(json.dumps({'run': str(run), 'result': summary['result'], 'frames': checked, 'error': error}))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
