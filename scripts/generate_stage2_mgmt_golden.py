"""Independent management-service vectors: real SNMP BER responses wrapped in AFDX frames."""
from pathlib import Path
import hashlib
import json
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_snmp_golden import generate as generate_snmp
from frozen_frame_reference import checksum, wire_for

MGMT_DA = bytes.fromhex("030000001244")
ES_MAC = bytes.fromhex("020000000009")
MANAGER_MAC = bytes.fromhex("02000000000a")
ES_IP = bytes((10, 0, 0, 1))
MANAGER_IP = bytes((10, 0, 0, 9))
OTHER_IP = bytes((10, 0, 0, 11))
MANAGER_PORT = 49152
SNMP_PORT = 161
OTHER_PORT = 9999
MGMT_VLID = 0x1244
BUSINESS_VLID = 0x1234
SNTP_VLID = 0x1245
SNTP_DA = bytes.fromhex("030000001245")
SNTP_SERVER_PORT = 123
SNTP_CLIENT_PORT = 49152
# The system test triggers the time exchange before any SNMP traffic and the RTC
# leaves reset on its documented initial value, so the request origin timestamp
# is known before the simulation runs.
SNTP_T1 = 0xE900000000000000
SNTP_RECEIVE = SNTP_T1 + 0x100000
# 80 clock cycles at 125 MHz expressed in NTP Q32.32 units.
SNTP_TRANSMIT = SNTP_RECEIVE + 2748
SNTP_STRATUM = 2
SNTP_POLL = 6
SNTP_PRECISION = 0xE8


def afdx_frame(da, sa, src_ip, dst_ip, src_port, dst_port, data, sn):
    """Ethernet/IPv4/UDP frame with the project wire profile: padding to the
    60-byte minimum, then the AFDX sequence number as the final payload byte."""
    total = 28 + len(data)
    ip = struct.pack("!BBHHHBBH4s4s", 0x45, 0, total, 0, 0x4000, 1, 17, 0, src_ip, dst_ip)
    ip = ip[:10] + struct.pack("!H", checksum(ip)) + ip[12:]
    udp = struct.pack("!HHHH", src_port, dst_port, 8 + len(data), 0)
    padding = bytes(max(0, 17 - len(data)))
    return da + sa + b"\x08\x00" + ip + udp + data + padding + bytes((sn,))


def sntp_packet(mode, stratum=0, origin=0, receive=0, transmit=0):
    """RFC4330 unicast packet: LI 0, VN 4, zero root delay and dispersion."""
    packet = bytearray(48)
    packet[0] = (4 << 3) | mode
    packet[1] = stratum
    packet[2] = SNTP_POLL
    packet[3] = SNTP_PRECISION
    packet[24:32] = origin.to_bytes(8, "big")
    packet[32:40] = receive.to_bytes(8, "big")
    packet[40:48] = transmit.to_bytes(8, "big")
    return bytes(packet)


def generate(out):
    out.mkdir(parents=True, exist_ok=True)
    generate_snmp(out / "snmp")
    snmp_cases = json.loads((out / "snmp" / "cases.json").read_text(encoding="utf-8"))
    requests = bytes.fromhex("".join((out / "snmp" / "requests.mem").read_text().split()))
    responses = bytes.fromhex("".join((out / "snmp" / "responses.mem").read_text().split()))

    rx = bytearray()
    tx = bytearray()
    cases = []
    state = {"rx_sn": 0, "tx_sn": 0}

    def add(name, kind, payload, sn, src_ip=MANAGER_IP, dst_port=SNMP_PORT, response=b"", note="", ticks=12345):
        client = afdx_frame(MGMT_DA, MANAGER_MAC, src_ip, ES_IP, MANAGER_PORT, dst_port, payload, sn)
        wire = wire_for(client)
        entry = {"id": len(cases), "name": name, "kind": kind, "sn": sn, "dst_port": dst_port,
                 "rx_offset": len(rx), "rx_length": len(wire), "payload_length": len(payload),
                 "expect_tx": bool(response), "tx_offset": len(tx), "tx_length": 0, "note": note,
                 "uptime_ticks": ticks}
        rx.extend(wire)
        if response:
            state["tx_sn"] += 1
            frame = afdx_frame(MGMT_DA, ES_MAC, ES_IP, MANAGER_IP, SNMP_PORT, MANAGER_PORT, response, state["tx_sn"])
            tx.extend(wire_for(frame))
            entry["tx_length"] = len(wire_for(frame))
        cases.append(entry)
        return entry

    # Time-service exchange: the client emits its request as soon as the system
    # test triggers it, before any SNMP traffic, so the request is the first frame
    # the shared builder puts on the wire. The server reply arrives through the
    # GMII receive port exactly like a management-station answer.
    request_wire = wire_for(afdx_frame(SNTP_DA, ES_MAC, ES_IP, MANAGER_IP, SNTP_CLIENT_PORT, SNTP_SERVER_PORT,
                                       sntp_packet(3, transmit=SNTP_T1), 1))
    cases.append({"id": len(cases), "name": "sntp_request", "kind": "sntp_request", "sn": 1,
                  "dst_port": SNTP_SERVER_PORT, "rx_offset": len(rx), "rx_length": 0, "payload_length": 48,
                  "expect_tx": True, "tx_offset": len(tx), "tx_length": len(request_wire),
                  "note": "client request on the time-service VL", "uptime_ticks": 12345})
    tx.extend(request_wire)
    reply_wire = wire_for(afdx_frame(SNTP_DA, MANAGER_MAC, MANAGER_IP, ES_IP, SNTP_SERVER_PORT, SNTP_CLIENT_PORT,
                                     sntp_packet(4, stratum=SNTP_STRATUM, origin=SNTP_T1, receive=SNTP_RECEIVE,
                                                 transmit=SNTP_TRANSMIT), 1))
    cases.append({"id": len(cases), "name": "sntp_exchange", "kind": "sntp_response", "sn": 1,
                  "dst_port": SNTP_CLIENT_PORT, "rx_offset": len(rx), "rx_length": len(reply_wire),
                  "payload_length": 48, "expect_tx": False, "tx_offset": len(tx), "tx_length": 0,
                  "note": "server reply injected through the GMII port", "uptime_ticks": 12345})
    rx.extend(reply_wire)

    for case in snmp_cases:
        if case["trap"]:
            continue
        state["rx_sn"] += 1
        request = requests[case["input_offset"]:case["input_offset"] + case["input_length"]]
        response = responses[case["output_offset"]:case["output_offset"] + case["output_length"]]
        add("snmp_" + case["name"], "snmp", request, state["rx_sn"], response=response,
            note=f"ber_case={case['name']}", ticks=case["uptime_ticks"])

    # Negative cases: unknown management port, repeated SN, unexpected peer.
    # The repeated frame must carry an SN the gate already saw, and the parser
    # rejection must not consume the next legal SN.
    seen_sn = state["rx_sn"] + 1
    state["rx_sn"] = seen_sn
    add("other_management_port", "unknown_port", requests[0:40], seen_sn, dst_port=OTHER_PORT,
        note="drained by the demux, no response")
    add("repeated_sequence_number", "bad_sn", requests[0:40], seen_sn,
        note="rejected by the management VL integrity gate")
    add("unexpected_peer_ip", "bad_peer", requests[0:40], seen_sn + 1, src_ip=OTHER_IP,
        note="rejected by the management VL parser before the gate")
    first = snmp_cases[0]
    recovery_request = requests[first["input_offset"]:first["input_offset"] + first["input_length"]]
    recovery_response = responses[first["output_offset"]:first["output_offset"] + first["output_length"]]
    add("recovery_get_sysdescr", "snmp", recovery_request, seen_sn + 1, response=recovery_response,
        note="recovery after the rejected frames")

    # Business frames share the same MAC and frame builder on the echo profile.
    for index, (length, sn) in enumerate(((64, 1), (1471, 2))):
        payload_length = length
        total = 28 + payload_length
        ip = struct.pack("!BBHHHBBH4s4s", 0x45, 0, total, 0, 0x4000, 1, 17, 0, ES_IP, bytes((224, 224, 0, 60)))
        ip = ip[:10] + struct.pack("!H", checksum(ip)) + ip[12:]
        udp = struct.pack("!HHHH", 24, 23, 8 + payload_length, 0)
        body = bytes((0x5A + index * 7 + position * 31 + (position >> 3)) & 0xFF for position in range(payload_length))
        padding = bytes(max(0, 17 - payload_length))
        client = MGMT_DA[:4] + bytes.fromhex("1234") + ES_MAC + b"\x08\x00" + ip + udp + body + padding + bytes((sn,))
        entry = {"id": len(cases), "name": f"business_echo_{index}", "kind": "business", "sn": sn, "dst_port": 23,
                 "rx_offset": len(rx), "rx_length": len(wire_for(client)), "payload_length": payload_length,
                 "expect_tx": True, "tx_offset": len(tx), "tx_length": len(wire_for(client)), "note": "business VL echo"}
        entry["uptime_ticks"] = 12345
        rx.extend(wire_for(client))
        tx.extend(wire_for(client))
        cases.append(entry)

    (out / "rx_wire.mem").write_text("".join(f"{byte:02X}\n" for byte in rx), encoding="ascii")
    (out / "expected_tx_wire.mem").write_text("".join(f"{byte:02X}\n" for byte in tx), encoding="ascii")
    (out / "frames.mem").write_text("".join(f"{case['rx_offset']:08X}{case['rx_length']:08X}\n" for case in cases), encoding="ascii")
    # Per-frame sysUpTime value: the system test drives the same tick input the
    # unit vectors assume, so one vector set covers both levels unchanged.
    (out / "uptime.mem").write_text("".join(f"{case['uptime_ticks']:08X}\n" for case in cases), encoding="ascii")
    (out / "constants.vh").write_text(f"localparam FRAME_COUNT={len(cases)}, RX_BYTES={len(rx)};\n", encoding="ascii")
    (out / "cases.json").write_text(json.dumps(cases, indent=2) + "\n", encoding="utf-8")
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file()}
    for p in sorted((out / "snmp").iterdir()):
        if p.is_file():
            hashes["snmp/" + p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    (out / "sha256.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    manifest = {"frames": len(cases), "rx_wire_bytes": len(rx), "expected_tx_frames": sum(1 for c in cases if c["expect_tx"]),
                "expected_tx_bytes": len(tx), "snmp_cases": len(snmp_cases), "snmp_golden": hashes["snmp/cases.json"],
                "sntp_t1": f"{SNTP_T1:016x}", "sntp_receive": f"{SNTP_RECEIVE:016x}",
                "sntp_transmit": f"{SNTP_TRANSMIT:016x}"}
    print("STAGE2_MGMT_GOLDEN = " + json.dumps(manifest))
    return manifest


if __name__ == "__main__":
    generate(Path(sys.argv[1] if len(sys.argv) > 1 else "build/logs/mgmt_golden"))
