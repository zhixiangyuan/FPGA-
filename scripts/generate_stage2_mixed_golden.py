"""Independent wire vectors for sustained business traffic plus management."""
from pathlib import Path
import hashlib
import json
from generate_stage2_mgmt_golden import generate as management_golden
from frozen_frame_reference import make_client, wire_for


def generate(out: Path, rounds=256, interval=8000, service_interval=600000):
    out.mkdir(parents=True, exist_ok=True)
    management_golden(out / 'management')
    mgmt = json.loads((out / 'management/cases.json').read_text())
    rx_mgmt = bytes.fromhex((out / 'management/rx_wire.mem').read_text())
    tx_mgmt = bytes.fromhex((out / 'management/expected_tx_wire.mem').read_text())
    cases = []
    for n in range(rounds):
        for vl in range(16):
            cid = n * 16 + vl
            client, _ = make_client(cid, 1471, n % 255 + 1)
            client = client[:4] + (0x1234 + vl).to_bytes(2, 'big') + client[6:]
            wire = wire_for(client)
            cases.append(dict(name=f'business_{cid}', kind='business', vlid=0x1234+vl,
                              nominal_cycle=1000+n*max(128000,16*interval)+vl*interval, payload_length=1471,
                              uptime_ticks=12345, rx=wire, tx=wire))
    request = mgmt[0]
    expected = [dict(name=request['name'], kind=request['kind'], vlid=0x1245,
                     tx=tx_mgmt[request['tx_offset']:request['tx_offset']+request['tx_length']],
                     input_id=None, payload_length=48)]
    service_index = 0
    for c in mgmt[1:]:
        if c['kind'] == 'business':
            continue
        nominal = 60000 if c['kind'] == 'sntp_response' else 100000+service_index*service_interval
        if c['kind'] != 'sntp_response':
            service_index += 1
        cases.append(dict(name=c['name'], kind=c['kind'], vlid=0x1245 if c['kind']=='sntp_response' else 0x1244,
                          nominal_cycle=nominal, payload_length=c['payload_length'],
                          uptime_ticks=c['uptime_ticks'],
                          rx=rx_mgmt[c['rx_offset']:c['rx_offset']+c['rx_length']],
                          tx=tx_mgmt[c['tx_offset']:c['tx_offset']+c['tx_length']]))
    # Serialize a single GMII source, preserving a full IFG. A service frame may
    # delay a business frame, so enforce the original minimum BAG per business VL.
    cases.sort(key=lambda c: c['nominal_cycle'])
    wire_blob = bytearray()
    next_free = 0
    previous_business = {}
    for cid, c in enumerate(cases):
        start = max(c['nominal_cycle'], next_free)
        if c['kind']=='business':
            start = max(start, previous_business.get(c['vlid'], -125000)+125000)
            previous_business[c['vlid']] = start
        c.update(id=cid, start_cycle=start, rx_offset=len(wire_blob), rx_length=len(c['rx']))
        wire_blob.extend(c.pop('rx'))
        next_free = start + c['rx_length'] + 12
        response = c.pop('tx')
        if response:
            expected.append(dict(name=c['name'], kind=c['kind'], vlid=c['vlid'], tx=response,
                                 input_id=cid, payload_length=c['payload_length']))
    tx_blob = bytearray()
    for c in expected:
        data = c.pop('tx')
        c.update(tx_offset=len(tx_blob), tx_length=len(data))
        tx_blob.extend(data)
    (out/'rx_wire.mem').write_text(''.join(f'{b:02x}\n' for b in wire_blob))
    (out/'expected_tx.mem').write_text(''.join(f'{b:02x}\n' for b in tx_blob))
    (out/'schedule.mem').write_text(''.join(f"{c['start_cycle']:08x}{c['rx_offset']:08x}{c['rx_length']:08x}{c['uptime_ticks']:08x}\n" for c in cases))
    (out/'constants.vh').write_text(f'localparam CASE_COUNT={len(cases)}, RX_BYTES={len(wire_blob)}, EXPECTED_FRAMES={len(expected)};\n')
    (out/'cases.json').write_text(json.dumps(cases, indent=2)+'\n')
    (out/'expected.json').write_text(json.dumps(expected, indent=2)+'\n')
    manifest=dict(business_frames=rounds*16, business_VLs=16, rounds_per_VL=rounds,
                  interval_cycles=interval, expected_frames=len(expected), input_frames=len(cases),
                  service_interval_cycles=service_interval,
                  rx_bytes=len(wire_blob), expected_tx_bytes=len(tx_blob), clock_ns=8,
                  minimum_BAG_cycles=125000, final_input_cycle=next_free)
    (out/'sha256.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                              for p in out.iterdir() if p.is_file()}, indent=2)+'\n')
    return manifest
