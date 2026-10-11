"""Independent file-level audit of the completed B2 candidate-loop evidence."""

from pathlib import Path
import csv
import hashlib
import json
import sys
import zlib


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mem(path: Path) -> bytes:
    return bytes(int(line, 16) for line in path.read_text(encoding="ascii").splitlines())


def main(run: Path) -> None:
    run = run.resolve(strict=True)
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    if summary["result"] != "PASS" or summary["exit_code"] != 0:
        raise ValueError("ModelSim summary is not PASS with exit code zero")
    transcript = (run / "transcript.log").read_text(errors="replace")
    for marker in ("B2_PROTOCOL_CANDIDATE_LOOP = PASS", "B2_PROTOCOL_FIFO_PRESSURE = PASS", "Errors: 0"):
        if marker not in transcript:
            raise ValueError(f"Missing raw marker: {marker}")
    if "** Fatal" in transcript or "** Error" in transcript:
        raise ValueError("Raw simulator error marker present")
    for item in summary["sources"]:
        if sha(Path(item["path"])) != item["sha256"]:
            raise ValueError(f"Source changed: {item['path']}")
        if sha(run / Path(item["path"]).name) != item["snapshot_sha256"]:
            raise ValueError(f"Snapshot changed: {item['path']}")
    if sha(run / "golden" / "sha256.json") != summary["golden_sha256"]:
        raise ValueError("Golden manifest changed")
    golden_hashes = json.loads((run / "golden" / "sha256.json").read_text())
    for name, expected in golden_hashes.items():
        if sha(run / "golden" / name) != expected:
            raise ValueError(f"Golden data changed: {name}")
    cases = json.loads((run / "golden" / "cases.json").read_text())
    client = mem(run / "golden" / "client.mem")
    wire = mem(run / "golden" / "wire.mem")
    payload = mem(run / "golden" / "payload.mem")
    fcs_valid = 0
    fcs_invalid = 0
    for case in cases:
        c = client[case["client_offset"]:case["client_offset"]+case["client_length"]]
        w = wire[case["wire_offset"]:case["wire_offset"]+case["wire_length"]]
        expected_fcs = (zlib.crc32(c) & 0xFFFFFFFF).to_bytes(4, "little")
        if w[:8] != bytes.fromhex("55555555555555d5") or w[8:-4] != c:
            raise ValueError(f"Wire framing differs from client: {case['name']}")
        if w[-4:] == expected_fcs:
            fcs_valid += 1
        else:
            fcs_invalid += 1
            if case["name"] != "bad_fcs":
                raise ValueError(f"Unexpected FCS mismatch: {case['name']}")
    if (fcs_valid, fcs_invalid) != (16, 1):
        raise ValueError("FCS case conservation failed")
    expected_tx = [0, 1, 2, 3, 4, 5, 16]
    tx_rows = list(csv.DictReader((run / "actual_tx_gmii.csv").open(newline="")))
    cursor = 0
    for case_id in expected_tx:
        case = cases[case_id]
        for index in range(case["wire_length"]):
            row = tx_rows[cursor]
            if (int(row["case_id"]), int(row["byte_index"]), int(row["data"], 16)) != (
                case_id, index, wire[case["wire_offset"]+index]
            ):
                raise ValueError(f"GMII CSV mismatch case={case_id} byte={index}")
            cursor += 1
    if cursor != len(tx_rows):
        raise ValueError("Unexpected GMII CSV trailing rows")
    expected_app = [0, 1, 2, 3, 4, 5, 16, 0, 1, 2, 3, 16]
    app_rows = list(csv.DictReader((run / "actual_payload.csv").open(newline="")))
    cursor = 0
    for case_id in expected_app:
        case = cases[case_id]
        for index in range(case["expected_payload_length"]):
            row = app_rows[cursor]
            if (int(row["case_id"]), int(row["byte_index"]), int(row["data"], 16),
                int(row["sop"]), int(row["eop"]), int(row["length"]), int(row["sn"])) != (
                case_id, index, payload[case["payload_offset"]+index],
                int(index == 0), int(index + 1 == case["expected_payload_length"]),
                case["expected_payload_length"], case["sn"]
            ):
                raise ValueError(f"Payload CSV mismatch case={case_id} byte={index}")
            cursor += 1
    if cursor != len(app_rows):
        raise ValueError("Unexpected application CSV trailing rows")
    wlf = run / "waves.wlf"
    if wlf.stat().st_size == 0:
        raise ValueError("WLF is empty")
    audit = {
        "result": "PASS", "run": str(run), "sn_policy": "BLOCKED_SN_RULE",
        "real_b1_tx_frames": len(expected_tx), "real_b1_tx_bytes": len(tx_rows),
        "candidate_payload_frames": len(expected_app), "candidate_payload_bytes": len(app_rows),
        "protocol_mutation_frames_with_correct_fcs": 9,
        "mac_fcs_error_frames": fcs_invalid,
        "wlf_bytes": wlf.stat().st_size, "wlf_sha256": sha(wlf),
        "transcript_sha256": sha(run / "transcript.log"),
        "tx_csv_sha256": sha(run / "actual_tx_gmii.csv"),
        "payload_csv_sha256": sha(run / "actual_payload.csv"),
    }
    (run / "verification.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
