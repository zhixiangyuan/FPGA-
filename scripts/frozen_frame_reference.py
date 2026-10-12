"""Independent B2 Ethernet/IP/UDP/Payload vectors; no RTL is imported."""

from pathlib import Path
import argparse
import hashlib
import json
import struct
import zlib

DA = bytes.fromhex("030000001234")
SA = bytes.fromhex("020000000009")
SRC_IP = bytes((10, 0, 0, 1))
DST_IP = bytes((224, 224, 0, 60))
PREAMBLE = bytes.fromhex("55555555555555d5")


def checksum(data: bytes) -> int:
    if len(data) & 1:
        data += b"\x00"
    total = sum((data[i] << 8) | data[i + 1] for i in range(0, len(data), 2))
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def payload(case_id: int, length: int) -> bytes:
    return bytes((0x35 + case_id * 13 + i * 37 + (i >> 2)) & 0xFF for i in range(length))


def make_client(case_id: int, length: int, sn: int) -> tuple[bytes, bytes]:
    data = payload(case_id, length)
    total = 28 + length
    ip = struct.pack("!BBHHHBBH4s4s", 0x45, 0, total, 0, 0x4000, 1, 17, 0, SRC_IP, DST_IP)
    ip = ip[:10] + struct.pack("!H", checksum(ip)) + ip[12:]
    udp = struct.pack("!HHHH", 24, 23, 8 + length, 0)
    frame = DA + SA + b"\x08\x00" + ip + udp + data + bytes(max(0, 17-length)) + bytes((sn,))
    assert len(frame) == 43 + length + max(0, 17-length)
    return frame, data


def wire_for(client: bytes, corrupt_fcs: bool = False) -> bytes:
    fcs = bytearray((zlib.crc32(client) & 0xFFFFFFFF).to_bytes(4, "little"))
    if corrupt_fcs:
        fcs[0] ^= 0x01
    return PREAMBLE + client + fcs


def write_mem(path: Path, blob: bytes) -> None:
    path.write_text("".join(f"{byte:02X}\n" for byte in blob), encoding="ascii")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    cases = []
    client_blob = bytearray()
    wire_blob = bytearray()
    payload_blob = bytearray()

    specs = [
        ("valid_p1",1,1,None,0), ("valid_p16",16,2,None,0),
        ("valid_p17",17,3,None,0), ("valid_p18",18,4,None,0),
        ("valid_p1471",1471,5,None,0), ("valid_p64",64,6,None,0),
        ("bad_da",18,7,"da",2), ("bad_vlid",18,7,"vlid",2),
        ("bad_ethertype",18,7,"ether",2),
        ("bad_ip_checksum",18,7,"ip_checksum",4),
        ("bad_ip_version",18,7,"ip_version",3),
        ("bad_udp_length",18,7,"udp_length",6),
        ("bad_udp_port",18,7,"udp_port",5),
        ("bad_padding",1,7,"padding",7),
        ("truncated_sn",64,7,"truncate",6),
        ("bad_fcs",18,7,"fcs",8),
        ("recovery",33,7,None,0),
    ]
    for case_id, (name, length, sn, mutation, reason) in enumerate(specs):
        client, app = make_client(case_id, length, sn)
        modified = bytearray(client)
        if mutation == "da": modified[0] ^= 0x02
        if mutation == "vlid": modified[5] ^= 0x01
        if mutation == "ether": modified[13] ^= 0x01
        if mutation == "ip_checksum": modified[25] ^= 0x01
        if mutation == "ip_version": modified[14] = 0x65
        if mutation == "udp_length": modified[39] ^= 0x01
        if mutation == "udp_port": modified[37] ^= 0x01
        if mutation == "padding": modified[43] = 0xA5
        if mutation == "truncate": modified.pop()
        client = bytes(modified)
        wire = wire_for(client, mutation == "fcs")
        case = {
            "id": case_id, "name": name, "payload_length": length,
            "sn": sn, "mutation": mutation, "expected_reason": reason,
            "expected_protocol_candidate": mutation is None,
            "expected_mac_accept": mutation != "fcs",
            "client_offset": len(client_blob), "client_length": len(client),
            "wire_offset": len(wire_blob), "wire_length": len(wire),
            "payload_offset": len(payload_blob), "expected_payload_length": len(app),
        }
        cases.append(case)
        client_blob.extend(client)
        wire_blob.extend(wire)
        payload_blob.extend(app)
    write_mem(out / "client.mem", client_blob)
    write_mem(out / "wire.mem", wire_blob)
    write_mem(out / "payload.mem", payload_blob)
    (out / "cases.json").write_text(json.dumps(cases, indent=2) + "\n", encoding="utf-8")
    fields = ("client_offset", "client_length", "wire_offset", "wire_length",
              "payload_offset", "expected_payload_length", "sn", "expected_reason")
    (out / "meta.mem").write_text(
        "".join("".join(f"{case[field]:08X}" for field in fields) + "\n" for case in cases),
        encoding="ascii",
    )
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file()}
    (out / "sha256.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    print(f"B2_GOLDEN = PASS cases={len(cases)} wire_bytes={len(wire_blob)}")


if __name__ == "__main__":
    main()
