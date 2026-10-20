"""Management-service system run: business echo plus SNMP over the real MAC."""
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_stage2_mgmt_golden import generate, SNTP_T1, SNTP_RECEIVE, SNTP_TRANSMIT, SNTP_VLID

ROOT = Path(__file__).resolve().parents[1]
MS = Path(os.environ.get('MODELSIM_BIN', r'D:\FPGA\Modlesim20.4\ModelSim20.4\win64'))
RTL = ('afdx_multi_vl_rx_parser.v', 'afdx_multi_vl_sn_gate.v', 'afdx_multi_vl_echo_queue.v', 'afdx_multi_vl_tx.v',
       'afdx_snmp_agent.v', 'afdx_service_message_fifo.v', 'afdx_service_tx_arbiter.v', 'afdx_management_rx_demux.v',
       'afdx_sntp_client.v', 'afdx_rtc_timebase.v', 'afdx_stage2_mgmt_top.v')
BUSINESS_VL = 0x1234
MGMT_VL = 0x1244


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--load-core',action='store_true');args=parser.parse_args()
    prefix='mgmt_load' if args.load_core else 'mgmt'
    parent = ROOT / 'build/logs'
    index = 1
    while (parent / f'{prefix}_{index:03d}').exists():
        index += 1
    run = parent / f'{prefix}_{index:03d}'
    run.mkdir(parents=True)
    sources = sorted((ROOT / 'vendor/frozen').glob('*.v')) + [ROOT / 'rtl' / n for n in RTL] + [ROOT / 'sim/tb_stage2_mgmt.sv']
    if args.load_core:
        from submission_sources import core_sources
        sources=core_sources()+[ROOT/'sim/tb_stage2_mgmt.sv']
    scripts = [Path(__file__), ROOT / 'scripts/generate_stage2_mgmt_golden.py',
               ROOT / 'scripts/generate_snmp_golden.py', ROOT / 'scripts/frozen_frame_reference.py']
    if args.load_core:scripts+=[ROOT/'scripts/submission_sources.py',ROOT/'scripts/prepare_stage2_mgmt_elinx.py']
    for path in sources + scripts:
        shutil.copy2(path, run / path.name)
    manifest = generate(run / 'golden')
    shutil.copy2(MS.parent / 'modelsim.ini', run / 'modelsim.ini')
    os.chmod(run / 'modelsim.ini', 0o666)
    commands = ['onerror {quit -code 2 -force}', 'vlib work', 'vmap work work']
    define='+define+MGMT_LOAD_CORE ' if args.load_core else ''
    commands += [f'vlog {define}{"-sv " if path.suffix == ".sv" else ""}+incdir+{run.as_posix()} {path.name}' for path in sources]
    commands += ['vopt -O5 +acc=nr+tb_stage2_mgmt work.tb_stage2_mgmt -o mgmt_optimized',
                 'vsim -t 1ps -wlf waves.wlf work.mgmt_optimized',
                 'log /tb_stage2_mgmt/reset /tb_stage2_mgmt/gmii_rxd /tb_stage2_mgmt/gmii_rx_dv /tb_stage2_mgmt/tx_data /tb_stage2_mgmt/tx_valid',
                 'run -all', 'quit -code 0 -force']
    (run / 'run.do').write_text('\n'.join(commands) + '\n', encoding='ascii')
    env = os.environ.copy()
    env.setdefault('MGLS_LICENSE_FILE', str(MS.parent / 'LICENSE.TXT'))
    command = [str(MS / 'vsim.exe'), '-batch', '-modelsimini', 'modelsim.ini', '-l', 'transcript.log', '-do', 'do run.do']
    summary = {'result': 'RUNNING', 'load_core':args.load_core, 'started_utc': datetime.now(timezone.utc).isoformat(), 'golden': manifest,
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
            filtered = [c for c in cases if c['kind'] in ('snmp', 'unknown_port', 'sntp_response')]
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
                expected_vl = {'business': BUSINESS_VL, 'sntp_request': SNTP_VLID}.get(case['kind'], MGMT_VL)
                assert vlid == expected_vl, f'wrong VLID on the wire for case {case["name"]}: {vlid:04x}'
                start = int(event['start_cycle'])
                if vlid in last_start:
                    gaps[vlid].append(start - last_start[vlid])
                last_start[vlid] = start
                # The time-service request is generated by the endpoint itself, so
                # it has no GMII input frame to measure a turnaround against.
                if case['id'] in inputs:
                    source = inputs[case['id']]
                    latencies.append({'case': case['name'], 'kind': case['kind'],
                                      'gmii_in_to_out_ns': (start - int(source['start_cycle'])) * 8})
                checked += 1
            assert offset == len(actual), 'unexplained trailing transmit bytes'
            assert min(gaps[BUSINESS_VL]) >= 125000, f'business BAG {min(gaps[BUSINESS_VL])}'
            # Every service VL must also respect the 1 ms minimum bag; a VL needs
            # at least two transmitted frames before an interval exists at all.
            for vlid, intervals in gaps.items():
                assert min(intervals) >= 125000, f'bag violation on VL {vlid:04x}: {min(intervals)}'
            counters = {row['key']: int(row['value'], 0) for row in csv.DictReader((run / 'counters.csv').open(newline=''))}
            service_frames = [c for c in cases if c['expect_tx'] and c['kind'] != 'business']
            assert counters['tx_frames'] == len(expected)
            assert counters['demux_routed'] == len(service_cases), counters['demux_routed']
            assert counters['demux_sntp_routed'] == 1, counters['demux_sntp_routed']
            assert counters['demux_dropped'] == 1 and counters['demux_last_dropped_port'] == 9999
            assert counters['mgmt_gate_rejected'] == 1
            assert counters['mgmt_gate_delivered'] == len(filtered)
            assert counters['arbiter_service_sent'] == len(service_frames)
            # Not every SNMP vector produces a reply: the malformed requests are
            # expected to leave the agent silent.
            snmp_replies = [c for c in service_cases if c['expect_tx']]
            assert counters['arbiter_snmp_sent'] == len(snmp_replies), counters['arbiter_snmp_sent']
            assert counters['arbiter_sntp_sent'] == 1, counters['arbiter_sntp_sent']
            assert counters['snmp_fifo_captured'] == counters['snmp_fifo_sent'] == len(snmp_replies)
            assert counters['sntp_fifo_captured'] == counters['sntp_fifo_sent'] == 1
            assert counters['snmp_fifo_overflow'] == 0 and counters['sntp_fifo_overflow'] == 0
            assert counters['snmp_trap'] == 0
            assert counters['business_gate_delivered'] == 2 and counters['application_sent'] == 2
            assert counters['application_error'] == 0 and counters['arbiter_service_error'] == 0
            # Both receive parsers observe every wire frame on the shared MAC,
            # so each one also counts the frames that belong to the other path.
            business_cases = [c for c in cases if c['kind'] == 'business']
            wrong_peer_cases = [c for c in cases if c['kind'] == 'bad_peer']
            # Every injected frame reaches both parsers; the time-service request
            # case carries no GMII input of its own.
            injected = [c for c in cases if c['rx_length'] > 0]
            assert counters['business_parser_accepted'] == len(business_cases), counters['business_parser_accepted']
            assert counters['business_parser_rejected'] == len(injected) - len(business_cases), \
                counters['business_parser_rejected']
            assert counters['mgmt_parser_rejected'] == len(business_cases) + len(wrong_peer_cases), \
                counters['mgmt_parser_rejected']
            assert counters['mgmt_parser_accepted'] == len(injected) - len(business_cases) - len(wrong_peer_cases), \
                counters['mgmt_parser_accepted']
            # Independent time-service check. The reply carries the timestamps the
            # golden generator chose and the request origin must be exactly the
            # documented RTC reset value the testbench relies on; the receive
            # timestamp is whatever the RTC read on the first byte of the injected
            # reply. Offset and round-trip delay are then recomputed here with NTP
            # modular arithmetic and compared against what the RTC reported.
            assert counters['sntp_accepted'] == 1 and counters['sntp_rejected'] == 0, counters['sntp_accepted']
            assert counters['sntp_timeout'] == 0, counters['sntp_timeout']
            assert counters['rtc_synchronized'] == 1 and counters['rtc_sync_count'] == 1
            assert counters['rtc_error_count'] == 0, counters['rtc_error_count']
            t1, t2, t3, t4 = (counters[key] for key in ('sntp_t1', 'sntp_t2', 'sntp_t3', 'sntp_t4'))
            assert t1 == SNTP_T1 == counters['sntp_request_t1'], (
                f'request origin {t1:016x} vs {counters["sntp_request_t1"]:016x}')
            assert t2 == SNTP_RECEIVE and t3 == SNTP_TRANSMIT, 'server timestamps on the wire'
            assert t4 == counters['sntp_rx_timestamp'], 'receive timestamp is the GMII arrival read of the RTC'
            mask = (1 << 64) - 1

            def signed(value):
                return value - (1 << 64) if value >> 63 else value

            network_elapsed = signed((t4 - t1) & mask)
            server_elapsed = signed((t3 - t2) & mask)
            delay = network_elapsed - server_elapsed
            offset = (signed((t2 - t1) & mask) + signed((t3 - t4) & mask)) >> 1
            assert network_elapsed >= 0 and server_elapsed >= 0, 'NTP interval went backwards'
            assert 0 <= delay <= (1 << 32), f'round-trip delay {delay} outside the one-second bound'
            assert counters['rtc_last_delay'] == delay, (counters['rtc_last_delay'], delay)
            assert counters['rtc_last_offset'] == (offset & mask), (counters['rtc_last_offset'], offset)
            evidence = {
                'frames_compared': checked, 'service_responses': len(service_frames),
                'snmp_ber_cases_over_the_link': len(service_cases),
                'time_service': {'accepted': counters['sntp_accepted'], 'synchronized': counters['rtc_synchronized'],
                                 'request_origin': f'{t1:016x}', 'delay_ntp_units': delay, 'offset_ntp_units': offset},
                'negative_cases': {'unknown_port_drained': counters['demux_dropped'],
                                   'parser_rejected_peer': counters['mgmt_parser_rejected'],
                                   'gate_rejected_duplicate_sn': counters['mgmt_gate_rejected']},
                'counters': counters,
                'bag_cycles': {hex(BUSINESS_VL): {'min': min(gaps[BUSINESS_VL]), 'max': max(gaps[BUSINESS_VL])},
                               hex(MGMT_VL): {'min': min(gaps[MGMT_VL]), 'max': max(gaps[MGMT_VL])},
                               hex(SNTP_VLID): {'frames': 1}},
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
