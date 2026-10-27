"""Application-only real dual-MAC RTL regression, independent wire/app oracle."""
from pathlib import Path
from datetime import datetime, timezone
import csv, hashlib, json, os, shutil, subprocess, zlib
from frozen_frame_reference import make_client, wire_for
from generate_stage2_mgmt_golden import afdx_frame, sntp_packet, ES_MAC, ES_IP, MANAGER_IP
from modelsim_support import prepare_ini

ROOT = Path(__file__).resolve().parents[1]
MS = Path(os.environ.get('MODELSIM_BIN', r'D:\FPGA\Modlesim20.4\ModelSim20.4\win64'))

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def sources():
    names = ('afdx_app_tx_queue.v', 'afdx_redundant_rx.v', 'afdx_competition_core.v', 'afdx_mac_rx_buffered.v',
             'afdx_multi_vl_tx.v', 'afdx_multi_vl_rx_parser.v', 'competition/AFDX_top.v',
             'afdx_management_plane.v', 'afdx_poll_timer.v', 'afdx_snmp_agent.v',
             'afdx_service_message_fifo.v','afdx_sntp_client.v','afdx_rtc_timebase.v',
             'afdx_tftp_engine.v','afdx_atomic_file_store.v','afdx_615a_error_decoder.v',
             'afdx_615a_endpoint.v','afdx_load_message_fifo.v','afdx_management_rx_demux_615a.v',
             'afdx_service_tx_arbiter_615a.v')
    return sorted((ROOT/'vendor/frozen').glob('*.v')) + [ROOT/'rtl'/n for n in names]

def verify(run):
    offered = list(csv.DictReader((run/'inputs.csv').open()))
    good = offered[:688]
    assert len(good) == 688 and len(offered) == 691
    expected = {}
    for row in good:
        cid, vl, length = (int(row[k]) for k in ('id', 'vl', 'length'))
        frame, payload = make_client(cid, length, 1)
        expected[cid] = (vl, payload, int(row['cycle']))
    received, packet, started = {}, bytearray(), None
    for r in csv.DictReader((run/'application.csv').open()):
        if int(r['sop']):
            assert not packet
            started = int(r['cycle'])
        packet.append(int(r['data']))
        if int(r['eop']):
            vl = int.from_bytes(packet[:2], 'big')
            candidates = [cid for cid, (v, p, _) in expected.items() if cid not in received and v == vl and p == packet[2:]]
            assert candidates, f'unexpected/duplicate application packet VL={vl:04x}'
            cid = min(candidates)
            received[cid] = dict(start=started, end=int(r['cycle']), vl=vl)
            packet.clear()
    assert not packet and len(received) == len(expected)
    wire_streams = []
    for name in ('wire_a.csv', 'wire_b.csv'):
        frames, data, start, last = [], bytearray(), None, None
        for r in csv.DictReader((run/name).open()):
            cycle = int(r['cycle'])
            if last is not None and cycle != last+1:
                frames.append((start, bytes(data))); data.clear(); start = None
            if start is None:
                start = cycle
            data.append(int(r['data'], 16)); last = cycle
        if data:
            frames.append((start, bytes(data)))
        wire_streams.append(frames)
    assert wire_streams[0] == wire_streams[1], 'A/B transmit forks differ'
    assert len(wire_streams[0]) == len(expected)+1
    sn, last_start, gaps, by_vl = {}, {}, [], {}
    for start, wire in wire_streams[0]:
        assert wire[:8] == bytes.fromhex('55555555555555d5')
        vl = int.from_bytes(wire[12:14], 'big')
        if vl == 0x12b5:
            t1=0xe900000000000000+8192*(1<<32)//125000000
            assert wire==wire_for(afdx_frame(bytes.fromhex('0300000012b5'),ES_MAC,ES_IP,MANAGER_IP,
                                           49152,123,sntp_packet(3,transmit=t1),1))
            continue
        length = int.from_bytes(wire[46:48], 'big')-8
        payload = wire[50:50+length]
        candidates = [cid for cid, (v, p, _) in expected.items() if cid not in by_vl and v == vl and p == payload]
        assert candidates
        cid = min(candidates); by_vl[cid] = vl
        seq = sn.get(vl, 0) % 255+1; sn[vl] = seq
        frame, _ = make_client(cid, length, seq)
        frame = frame[:4]+vl.to_bytes(2, 'big')+frame[6:]
        assert wire == wire_for(frame), f'wire oracle mismatch cid={cid}'
        if vl in last_start:
            gaps.append(start-last_start[vl])
        last_start[vl] = start
    assert min(gaps) >= 125000
    load_ids = range(176, 688)
    first = expected[176][2]
    end_input = expected[687][2]+1473
    end_output = max(received[c]['end'] for c in load_ids)
    payload_bytes = sum(len(expected[c][1]) for c in load_ids)
    input_rate = payload_bytes*1000/(end_input-first)
    delivered_rate = payload_bytes*1000/(end_output-first)
    latency = [(received[c]['end']-expected[c][2])*8 for c in load_ids]
    jitter = []
    for vl in range(0x1234, 0x1244):
        samples = [(received[c]['end']-expected[c][2])*8 for c in load_ids if expected[c][0] == vl]
        jitter.append(max(samples)-min(samples))
    assert input_rate >= 100 and delivered_rate >= 100
    assert max(latency) < 2000000 and max(jitter) <= 50000
    return dict(application_messages=len(received), TX_VLs=128, RX_configured_VLs=4096,
                RX_all_VL_functional_coverage='NOT RUN by this integration test',
                application_payload_input_Mbps=input_rate, application_payload_delivered_Mbps=delivered_rate,
                max_application_first_to_last_ns=max(latency), max_same_VL_same_length_range_ns=max(jitter),
                minimum_BAG_cycles=min(gaps), payload_lengths=[1,64,512,1471],
                dual_network_wire_oracle=True, single_network_fault_recovery=True,
                delayed_B_cycles=64, backpressure=True, synthesis='NOT RUN', VO='NOT RUN',
                management_in_new_wrapper='enabled; automatic SNTP shares sender during application traffic')

def main():
    i = 1
    while (ROOT/f'build/logs/competition_{i:03d}').exists():
        i += 1
    run = ROOT/f'build/logs/competition_{i:03d}'; run.mkdir(parents=True)
    files = sources()+[ROOT/'sim/tb_competition.sv']
    inputs = files+[Path(__file__), ROOT/'scripts/frozen_frame_reference.py', ROOT/'scripts/modelsim_support.py',
                    ROOT/'scripts/generate_stage2_mgmt_golden.py']
    for p in inputs:
        shutil.copy2(p, run/p.name)
    prepare_ini(run, MS)
    commands = ['onerror {quit -code 2 -force}', 'vlib work']
    commands += [f'vlog {"-sv " if p.suffix == ".sv" else ""}{p.name}' for p in files]
    commands += ['vopt -O5 work.tb_competition -o competition_opt',
                 'vsim -t 1ps work.competition_opt', 'run -all', 'quit -code 0 -force']
    (run/'run.do').write_text('\n'.join(commands)+'\n')
    summary = dict(result='RUNNING', started_utc=datetime.now(timezone.utc).isoformat(),
                   inputs={str(p.relative_to(ROOT)): sha(p) for p in inputs}, clock_ns=8, BAG_cycles=125000)
    proof = run/'summary.json'; proof.write_text(json.dumps(summary, indent=2)+'\n')
    env = os.environ.copy(); env.setdefault('MGLS_LICENSE_FILE', str(MS.parent/'LICENSE.TXT'))
    print(f'COMPETITION_RUN {run}', flush=True)
    with (run/'console.log').open('wb') as log:
        process = subprocess.Popen([str(MS/'vsim.exe'), '-batch', '-modelsimini', 'modelsim.ini',
                                    '-l', 'transcript.log', '-do', 'do run.do'], cwd=run, env=env,
                                   stdout=log, stderr=subprocess.STDOUT)
        summary['pid'] = process.pid; proof.write_text(json.dumps(summary, indent=2)+'\n')
        code = process.wait(timeout=2400)
    transcript = (run/'transcript.log').read_text(errors='replace')
    error, evidence = None, {}
    passed = code == 0 and 'COMPETITION_PASS' in transcript and '** Error' not in transcript and '** Fatal' not in transcript
    if passed:
        try:
            evidence = verify(run)
            assert all(sha(ROOT/n) == h for n, h in summary['inputs'].items()), 'inputs changed during run'
        except Exception as exc:
            passed = False; error = repr(exc)
    summary.update(result='PASS' if passed else 'FAIL', exit_code=code, error=error, evidence=evidence,
                   completed_utc=datetime.now(timezone.utc).isoformat())
    proof.write_text(json.dumps(summary, indent=2)+'\n')
    print(transcript[-2600:]); print(json.dumps(dict(run=str(run), result=summary['result'], error=error, evidence=evidence), indent=2))
    return 0 if passed else 1

if __name__ == '__main__':
    raise SystemExit(main())
