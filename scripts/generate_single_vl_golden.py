from pathlib import Path
import argparse
import hashlib
import json
import struct
import zlib

DA_CONST = 0x03000000
VLID = 0x1234
DEST_MAC = bytes([0x03, 0x00, 0x00, 0x00, 0x12, 0x34])
SRC_MAC = bytes.fromhex("02 00 00 00 00 09")
SRC_IP = bytes([10, 0, 0, 1])
DST_IP = bytes([224, 224, 0, 60])
SRC_PORT = 24
DST_PORT = 23
TTL = 1
ETH_PREAMBLE_SFD = bytes([0x55] * 7 + [0xD5])

BOUNDARY_LENGTHS = [1, 16, 17, 18, 1471, 2, 7, 64, 255, 512, 1024]


def internet_checksum(header: bytes) -> int:
    if len(header) & 1:
        header += b"\x00"
    total = sum((header[i] << 8) | header[i + 1] for i in range(0, len(header), 2))
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def payload_for(frame_id: int, length: int) -> bytes:
    return bytes((0x53 + frame_id * 17 + i * 29 + (i >> 3)) & 0xFF for i in range(length))


def make_frame(frame_id: int, payload_length: int, sequence: int):
    payload = payload_for(frame_id, payload_length)
    padding = max(0, 17 - payload_length)
    udp_length = 8 + payload_length
    ipv4_total = 20 + udp_length
    ipv4_zero = struct.pack(
        "!BBHHHBBH4s4s",
        0x45, 0x00, ipv4_total, 0x0000, 0x4000,
        TTL, 17, 0x0000, SRC_IP, DST_IP,
    )
    ip_checksum = internet_checksum(ipv4_zero)
    ipv4 = ipv4_zero[:10] + struct.pack("!H", ip_checksum) + ipv4_zero[12:]
    udp = struct.pack("!HHHH", SRC_PORT, DST_PORT, udp_length, 0)
    client = DEST_MAC + SRC_MAC + b"\x08\x00" + ipv4 + udp + payload + bytes(padding) + bytes([sequence])
    fcs_value = zlib.crc32(client) & 0xFFFFFFFF
    fcs = fcs_value.to_bytes(4, "little")
    wire = ETH_PREAMBLE_SFD + client + fcs

    assert 1 <= payload_length <= 1471
    assert len(client) == 43 + payload_length + padding
    assert 60 <= len(client) <= 1514
    assert len(wire) == 8 + len(client) + 4
    assert internet_checksum(ipv4) == 0
    assert int.from_bytes(ipv4[2:4], "big") == 28 + payload_length
    assert int.from_bytes(udp[4:6], "big") == 8 + payload_length
    assert udp[6:8] == b"\x00\x00"
    assert client[-1] == sequence
    return payload, client, wire, {
        "frame_id": frame_id,
        "payload_length": payload_length,
        "padding_length": padding,
        "sequence": sequence,
        "ipv4_total_length": ipv4_total,
        "ipv4_checksum": ip_checksum,
        "udp_length": udp_length,
        "udp_checksum": 0,
        "client_length": len(client),
        "wire_length": len(wire),
        "fcs_hex_on_wire": fcs.hex(),
    }


def write_mem(path: Path, data: bytes) -> None:
    path.write_text("".join(f"{b:02X}\n" for b in data), encoding="ascii")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    frames = []
    frame_id = 0
    sn = 1
    for length in BOUNDARY_LENGTHS:
        frames.append((0, frame_id, length, sn))
        frame_id += 1
        sn = 1 if sn == 255 else sn + 1
    # After invalid descriptors/frames, one legal recovery frame must keep SN=12.
    frames.append((0, frame_id, 33, sn))
    frame_id += 1

    # A reset starts a new sender instance. Exercise every ordinary sequence
    # number and the 255 -> 1 wrap without force or a hidden state override.
    sn = 1
    for _ in range(256):
        frames.append((1, frame_id, 1, sn))
        frame_id += 1
        sn = 1 if sn == 255 else sn + 1

    payload_blob = bytearray()
    client_blob = bytearray()
    wire_blob = bytearray()
    metadata = []
    json_frames = []
    for group, fid, payload_length, sequence in frames:
        payload, client, wire, info = make_frame(fid, payload_length, sequence)
        info.update({
            "group": group,
            "payload_offset": len(payload_blob),
            "client_offset": len(client_blob),
            "wire_offset": len(wire_blob),
        })
        payload_blob.extend(payload)
        client_blob.extend(client)
        wire_blob.extend(wire)
        metadata.append(
            f"{info['payload_offset']:08X}{payload_length:04X}"
            f"{info['client_offset']:08X}{len(client):04X}"
            f"{info['wire_offset']:08X}{len(wire):04X}"
            f"{sequence:02X}{info['padding_length']:02X}"
            f"{info['ipv4_checksum']:04X}{info['ipv4_total_length']:04X}"
            f"{info['udp_length']:04X}{group:02X}"
        )
        json_frames.append(info)

    write_mem(out / "golden_payload.mem", bytes(payload_blob))
    write_mem(out / "golden_client.mem", bytes(client_blob))
    write_mem(out / "golden_wire.mem", bytes(wire_blob))
    (out / "golden_meta.mem").write_text("\n".join(metadata) + "\n", encoding="ascii")
    (out / "golden_meta.vh").write_text(
        "\n".join([
            f"localparam integer GOLDEN_FRAME_COUNT = {len(frames)};",
            f"localparam integer GOLDEN_PAYLOAD_BYTES = {len(payload_blob)};",
            f"localparam integer GOLDEN_CLIENT_BYTES = {len(client_blob)};",
            f"localparam integer GOLDEN_WIRE_BYTES = {len(wire_blob)};",
            "localparam integer GOLDEN_META_WIDTH = 216;",
            "",
        ]),
        encoding="ascii",
    )
    manifest = {
        "seed_method": "deterministic payload formula; Python stdlib only",
        "configuration": {
            "da_const32": f"0x{DA_CONST:08X}", "vlid": f"0x{VLID:04X}",
            "destination_mac": DEST_MAC.hex(), "source_mac": SRC_MAC.hex(),
            "source_ip": ".".join(map(str, SRC_IP)), "destination_ip": ".".join(map(str, DST_IP)),
            "source_udp_port": SRC_PORT, "destination_udp_port": DST_PORT,
            "ttl": TTL, "udp_checksum": 0,
        },
        "groups": {
            "0": {"name": "length boundaries plus error recovery", "frames": len(BOUNDARY_LENGTHS) + 1, "sn_start": 1},
            "1": {"name": "ordinary SN wrap", "frames": 256, "sn_sequence": "1..255,1; sender reset between groups"},
        },
        "total_frames": len(frames),
        "frames": json_frames,
        "integrity_sources": {
            "ipv4": "independent Python one's-complement sum",
            "fcs": "Python zlib.crc32; transmitted least-significant byte first",
            "rtl_functions_reused": False,
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    hashes = {}
    for path in sorted(out.iterdir()):
        if path.is_file():
            hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (out / "sha256.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    print(f"GOLDEN_GENERATION = PASS frames={len(frames)} payload_bytes={len(payload_blob)} client_bytes={len(client_blob)} wire_bytes={len(wire_blob)}")
    print(f"GOLDEN_DIR = {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
