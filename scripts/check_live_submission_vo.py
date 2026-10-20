"""Read-only early checks of complete VO wire records; never a final verdict.

The active simulator, compiled library, inputs and summary are not modified.
Buffered or partial final CSV lines are ignored until a later invocation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import zlib
from datetime import datetime, timezone
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def complete_rows(path: Path) -> list[dict]:
    raw = path.read_bytes()
    end = raw.rfind(b"\n")
    if end < 0:
        return []
    return list(csv.DictReader(io.StringIO(raw[:end + 1].decode("ascii"))))


def compare_prefix(actual: list[dict], reference: list[dict], direction: str) -> dict:
    expected: dict[int, list[tuple[int, bytes]]] = {}
    for row in reference:
        data = bytes.fromhex(row["data"])
        vl = int.from_bytes(data[12:14], "big")
        expected.setdefault(vl, []).append((int(row["case_id"]), data))
    counts: dict[int, int] = {}
    last_start: dict[int, int] = {}
    last_cycle = 0
    for index, row in enumerate(actual):
        data = bytes.fromhex(row["data"])
        if len(data) != int(row["bytes"]) or len(data) < 72:
            raise ValueError(f"{direction} row {index}: invalid wire length")
        if data[:8] != bytes.fromhex("55555555555555d5"):
            raise ValueError(f"{direction} row {index}: invalid preamble")
        if zlib.crc32(data[8:-4]) != int.from_bytes(data[-4:], "little"):
            raise ValueError(f"{direction} row {index}: Ethernet FCS mismatch")
        vl = int.from_bytes(data[12:14], "big")
        position = counts.get(vl, 0)
        stream = expected.get(vl, [])
        if position >= len(stream) or (int(row["case_id"]), data) != stream[position]:
            raise ValueError(f"{direction} row {index}, VL {vl:04x}, position {position}: RTL/VO wire bytes or case differ")
        start = int(row["start_cycle"])
        if vl in last_start and start - last_start[vl] < 125000:
            raise ValueError(f"{direction} row {index}, VL {vl:04x}: BAG below 125000 cycles")
        if direction == "tx" and int(row["end_cycle"]) - start + 1 != len(data):
            raise ValueError(f"tx row {index}: inconsistent frame duration")
        last_start[vl] = start
        last_cycle = max(last_cycle, int(row.get("end_cycle", start + len(data) - 1)))
        counts[vl] = position + 1
    return dict(complete_frames=len(actual), reference_frames=len(reference),
                last_observed_cycle=last_cycle, last_observed_time_ms=last_cycle * 8e-6,
                per_VL_frames={f"{vl:04x}": count for vl, count in sorted(counts.items())})


def inspect(run: Path, reference: Path) -> dict:
    summary = json.loads((run / "summary.json").read_text())
    baseline = json.loads((reference / "summary.json").read_text())
    if baseline["result"] != "PASS" or not baseline["RTL_DUT_compiled"]:
        raise ValueError("RTL reference is not a completed RTL PASS")
    if summary["RTL_DUT_compiled"] or summary["force_used"] or summary["shortened_timers"]:
        raise ValueError("Run is not an unshortened real-VO candidate")
    if summary["clock_ns"] != 8 or summary["BAG_cycles"] != 125000:
        raise ValueError("Unexpected clock or BAG")
    for name, digest in summary["rtl_reference_hashes"].items():
        if sha(reference / name) != digest:
            raise ValueError(f"Reference changed: {name}")
    if baseline["golden"] != summary["golden"]:
        raise ValueError("RTL/VO Golden manifests differ")
    for name, digest in summary["golden"].items():
        if sha(run / "golden" / name) != digest:
            raise ValueError(f"VO Golden changed: {name}")
    evidence = {direction: compare_prefix(complete_rows(run / f"wire_{direction}.csv"),
                                          complete_rows(reference / f"wire_{direction}.csv"), direction)
                for direction in ("tx", "rx")}
    started = datetime.fromisoformat(summary["started_utc"])
    return dict(result="PREFIX_MATCH_ONLY", final_acceptance=False,
                official_runner_result=summary["result"],
                sampled_utc=datetime.now(timezone.utc).isoformat(),
                wall_elapsed_minutes=(datetime.now(timezone.utc) - started).total_seconds() / 60,
                run=str(run), reference=str(reference), evidence=evidence,
                note="Only completed CSV rows checked; buffered tail, missing future frames, full cases and final hashes remain for the official runner.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--rtl-reference", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = inspect(args.run.resolve(), args.rtl_reference.resolve())
    except (ValueError, KeyError, OSError) as exc:
        print(json.dumps(dict(result="CHECK_FAILED", final_acceptance=False, error=str(exc)), indent=2))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
