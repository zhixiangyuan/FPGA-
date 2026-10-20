"""Independent audit of a full real-VO ModelSim run against its Golden, provenance and archived V1.0 evidence."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import zlib
from pathlib import Path

EXPECTED_COMPILE_SOURCES = {"AFDX_top.vo", "tb_v1_netlist.sv", "altera_primitives.v", "220model.v", "stratix_atoms.v"}
TRANSCRIPT_MARKERS = ("V1_REAL_NETLIST = PASS", "V1_NETLIST_PRESSURE = PASS",
                      "V1_NETLIST_PARTIAL_RESET = PASS", "Errors: 0")
FROZEN_GOLDEN_CASES = 315
EXTERNAL_EVIDENCE = ("actual_tx.csv", "app_commits.csv", "decisions.csv", "input_events.csv", "frame_progress.csv")


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def mem(path: Path) -> bytes:
    return bytes(int(x, 16) for x in Path(path).read_text().splitlines())


def check_provenance(run: Path, summary: dict, proof: dict) -> dict:
    """Validate the DUT, its export chain and every recorded input snapshot."""
    assert summary["result"] == "PASS" and summary["exit_code"] == 0, "run is not a verified PASS"
    assert not proof.get("RTL_DUT_compiled"), "run compiled RTL instead of the real netlist"
    assert not proof.get("force_used"), "run used force, so it is not a plain functional test"
    dut = run / proof.get("DUT", "AFDX_top.vo")
    assert dut.is_file() and "module AFDX_top" in dut.read_text(encoding="utf-8", errors="replace"), f"not a functional AFDX_top netlist: {dut}"
    assert proof.get("dut_sha256", sha(dut)) == sha(dut), "DUT changed after the run"

    export_provenance = proof.get("dut_export_provenance")
    if export_provenance and Path(export_provenance).is_file():
        export = json.loads(Path(export_provenance).read_text(encoding="utf-8"))
        assert export["result"] == "PASS", "the exported VO does not come from a passing export"
        assert export["delivered_netlist_sha256"] == sha(dut), "DUT does not match its export provenance"
        assert export.get("synthesis_or_fit_executed") is False, "export unexpectedly ran synthesis or fit"

    snapshots = {}
    for row in summary.get("sources", []):
        snapshot = run / Path(row["path"]).name
        assert snapshot.is_file() and sha(snapshot) == row["snapshot_sha256"], f"input snapshot mismatch: {snapshot}"
        original = Path(row["path"])
        if original.exists():
            assert sha(original) == row["sha256"], f"input changed since the run: {original}"
        snapshots[snapshot.name] = row["snapshot_sha256"]
    for name, digest in proof.get("inputs_sha256", {}).items():
        assert sha(run / name) == digest, f"input snapshot mismatch: {name}"
        snapshots[name] = digest
    assert EXPECTED_COMPILE_SOURCES <= set(snapshots), "recorded inputs do not cover the compiled DUT and Testbench"

    reference = proof.get("reference_run")
    reference_checked = False
    if reference and Path(reference).is_dir() and proof.get("reference_summary_sha256"):
        assert sha(Path(reference) / "summary.json") == proof["reference_summary_sha256"], "archived reference run changed"
        reference_checked = True
    return {"snapshots": snapshots, "reference_checked": reference_checked}


def check_golden(run: Path, summary: dict, proof: dict) -> list:
    golden = run / "golden"
    manifest = golden / "sha256.json"
    recorded = summary.get("golden_sha256") or proof["golden_manifest_sha256"]
    assert sha(manifest) == recorded, "Golden manifest does not match the frozen V1.0 evidence"
    for name, digest in json.loads(manifest.read_text(encoding="utf-8")).items():
        assert sha(golden / name) == digest, f"Golden file changed: {name}"
    transcript = (run / "transcript.log").read_text(encoding="utf-8", errors="replace")
    assert all(marker in transcript for marker in TRANSCRIPT_MARKERS), "transcript lacks a required PASS marker"
    assert "** Fatal" not in transcript and "** Error" not in transcript, "transcript reports simulator errors"
    cases = json.loads((golden / "cases.json").read_text(encoding="utf-8"))
    assert len(cases) == FROZEN_GOLDEN_CASES, f"Golden scenario count changed: {len(cases)}"
    return cases


def audit_external_bytes(run: Path, cases: list) -> dict:
    """Rebuild every external TX frame and every application commit straight from the Golden."""
    golden = run / "golden"
    outgoing = mem(golden / "outgoing.mem")
    incoming = mem(golden / "incoming.mem")
    expected_tx = [c for c in cases if c["action"] == 0]
    apps = [c for c in cases if c["action"] in (0, 6)]

    rows = list(csv.DictReader((run / "actual_tx.csv").open(newline="")))
    index = 0
    starts = []
    for case in expected_tx:
        blob = outgoing[case["outgoing_offset"]:case["outgoing_offset"] + case["outgoing_length"]]
        start = int(rows[index]["cycle"])
        starts.append((case, start))
        assert blob[-5] == case["tx_sn"], f"Golden TX SN mismatch in case {case['id']}"
        assert blob[-4:] == (zlib.crc32(blob[8:-4]) & 0xFFFFFFFF).to_bytes(4, "little"), f"Golden FCS mismatch in case {case['id']}"
        for offset in range(case["outgoing_length"]):
            row = rows[index]
            assert (int(row["case_id"]), int(row["byte_index"]), int(row["data"], 16)) == (case["id"], offset, blob[offset]), \
                f"external TX byte mismatch in case {case['id']} byte {offset}"
            assert int(row["cycle"]) == start + offset, f"external TX cycle mismatch in case {case['id']}"
            index += 1
    assert index == len(rows) == 22840, f"external TX byte count changed: {len(rows)}"
    assert len(starts) == 295, f"external TX frame count changed: {len(starts)}"

    commits = list(csv.DictReader((run / "app_commits.csv").open(newline="")))
    assert len(commits) == len(apps) == 296, "application commit count does not match the Golden"
    for row, case in zip(commits, apps):
        assert (int(row["case_id"]), int(row["length"]), int(row["rx_sn"])) == (case["id"], case["payload_length"], case["rx_sn"]), \
            f"application commit mismatch in case {case['id']}"

    epoch = -1
    app = tx = 0
    counts = {}
    for case in cases:
        if case["epoch"] != epoch:
            epoch = case["epoch"]
            app = tx = 0
        app += case["action"] in (0, 6)
        tx += case["action"] == 0
        counts[case["id"]] = (app, tx)
    decisions = list(csv.DictReader((run / "decisions.csv").open(newline="")))
    selected = [c for c in cases if c["action"] not in (5, 7) and not (c["name"].startswith("pressure_retained_") and c["rx_sn"] != 16)]
    assert len(decisions) == 308, f"PSN decision count changed: {len(decisions)}"
    assert [int(r["case_id"]) for r in decisions] == [c["id"] for c in selected], "PSN decisions do not follow the expected scenario order"
    for row, case in zip(decisions, selected):
        assert (int(row["psn"]), int(row["valid"]), int(row["commits"]), int(row["sent"])) == \
            (case["expected_psn"], int(case["expected_valid"]), *counts[case["id"]]), f"PSN decision mismatch in case {case['id']}"

    inputs = list(csv.DictReader((run / "input_events.csv").open(newline="")))
    assert [int(r["case_id"]) for r in inputs] == list(range(len(cases))), "input event order does not follow the Golden scenarios"
    fcs_errors = 0
    for row, case in zip(inputs, cases):
        assert int(row["action"]) == case["action"], f"input action mismatch in case {case['id']}"
        assert int(row["bytes"]) == (100 if case["action"] == 7 else case["incoming_length"]), f"input length mismatch in case {case['id']}"
        assert int(row["end_cycle"]) - int(row["start_cycle"]) + 1 == int(row["bytes"]), f"input window mismatch in case {case['id']}"
        blob = incoming[case["incoming_offset"]:case["incoming_offset"] + case["incoming_length"]]
        if blob[-4:] != (zlib.crc32(blob[8:-4]) & 0xFFFFFFFF).to_bytes(4, "little"):
            assert case["mutation"] == "fcs", f"unexplained corrupt input in case {case['id']}"
            fcs_errors += 1

    gaps = [b - a for (ca, a), (cb, b) in zip(starts, starts[1:]) if ca["epoch"] == cb["epoch"]]
    assert len(gaps) == 289, f"BAG gap count changed: {len(gaps)}"
    assert min(gaps) >= 125000 and max(gaps) <= 137500, f"BAG out of contract: {min(gaps)}..{max(gaps)} cycles"
    assert (run / "waves.wlf").stat().st_size > 0, "no waveform was written"
    return {"external_TX_frames": len(starts), "external_TX_bytes": len(rows), "actual_app_bank_commits": len(commits),
            "external_echo_payload_bytes": sum(c["payload_length"] for c in expected_tx), "actual_PSN_decisions": len(decisions),
            "BAG_gaps": len(gaps), "min_BAG_cycles": min(gaps), "max_BAG_cycles": max(gaps), "intentional_FCS_error": fcs_errors}


def compare_with_reference(run: Path, proof: dict) -> dict:
    """Cross-check this run against the archived V1.0 real-VO evidence directory."""
    reference = proof.get("reference_run")
    if not reference or not Path(reference).is_dir():
        return {"compared": False, "reason": "archived reference run not present"}
    reference = Path(reference)
    result = {"compared": True, "reference_run": str(reference), "files": {}}
    for name in EXTERNAL_EVIDENCE + ("golden/sha256.json", "DUT_netlist"):
        current = run / ("golden/sha256.json" if name == "golden/sha256.json" else "AFDX_top.vo" if name == "DUT_netlist" else name)
        archived = reference / ("golden/sha256.json" if name == "golden/sha256.json" else "AFDX_top.vo" if name == "DUT_netlist" else name)
        if not archived.is_file():
            result["files"][name] = "absent"
            continue
        same = sha(current) == sha(archived)
        result["files"][name] = "identical" if same else "different"
        if name in EXTERNAL_EVIDENCE:
            assert same, f"external behaviour differs from the archived V1.0 run: {name}"
    result["external_behaviour_identical"] = all(v == "identical" for k, v in result["files"].items() if k in EXTERNAL_EVIDENCE)
    result["netlist_differs_from_archived_export"] = result["files"].get("DUT_netlist") == "different"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="build/logs/netlist_NNN produced by run_v1_netlist.py")
    parser.add_argument("--compare-reference", action="store_true", default=True,
                        help="cross-check external evidence against the archived reference run (default: on)")
    parser.add_argument("--no-compare-reference", dest="compare_reference", action="store_false")
    args = parser.parse_args()
    run = args.run.resolve()
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    proof = json.loads((run / "provenance.json").read_text(encoding="utf-8"))

    provenance = check_provenance(run, summary, proof)
    cases = check_golden(run, summary, proof)
    measured = audit_external_bytes(run, cases)
    comparison = compare_with_reference(run, proof) if args.compare_reference else {"compared": False, "reason": "disabled"}
    result = {
        "result": "PASS",
        "scope": "real exported AFDX_top functional netlist; external bytes rebuilt from the frozen Golden plus real application RAM commits and retained PSN",
        "run": str(run),
        "summary_sha256": sha(run / "summary.json"),
        "provenance_sha256": sha(run / "provenance.json"),
        "dut_sha256": sha(run / "AFDX_top.vo"),
        "dut_source": proof.get("dut_source"),
        "dut_export_provenance": proof.get("dut_export_provenance"),
        "compile_sources_sha256": provenance["snapshots"],
        "reference_summary_sha256_verified": provenance["reference_checked"],
        "golden_manifest_sha256": sha(run / "golden" / "sha256.json"),
        "golden_cases": len(cases),
        "SN_wrap": 256,
        **measured,
        "committed_payload_bytes_metadata": sum(c["payload_length"] for c in cases if c["action"] in (0, 6)),
        "raw_internal_app_byte_compare": "covered by the frozen-current RTL run; not claimed for optimized VO nets",
        "pressure_retained": 6,
        "capacity_drop": 1,
        "reset_cancel": 1,
        "partial_reset": 1,
        "reference_comparison": comparison,
        "POST_SYNTH_TIMING": "NOT VERIFIED",
        "EQ6_NATIVE_NETLIST_EQUIVALENCE": "NOT VERIFIED",
    }
    result["artifact_hashes"] = {p.name: sha(p) for p in run.iterdir() if p.is_file() and p.name not in {"verification.json", "summary.json"}}
    (run / "verification.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "artifact_hashes"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
