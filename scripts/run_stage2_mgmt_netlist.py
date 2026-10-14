"""Run and independently check the full management Golden suite on real VO."""
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_stage2_mgmt_golden import generate, SNTP_VLID

ROOT = Path(__file__).resolve().parents[1]
MS = Path(os.environ.get("MODELSIM_BIN", r"D:\FPGA\Modlesim20.4\ModelSim20.4\win64"))
REF = ROOT / "build/logs/netlist_001"
BUSINESS_VL = 0x1234
MGMT_VL = 0x1244
FROZEN = tuple(sorted((ROOT / "vendor/frozen").glob("*.v")))
RTL = ("afdx_multi_vl_rx_parser.v", "afdx_multi_vl_sn_gate.v", "afdx_multi_vl_echo_queue.v",
       "afdx_multi_vl_tx.v", "afdx_snmp_agent.v", "afdx_service_message_fifo.v",
       "afdx_service_tx_arbiter.v", "afdx_management_rx_demux.v", "afdx_sntp_client.v",
       "afdx_rtc_timebase.v")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dut-vo", type=Path, required=True)
    parser.add_argument("--dut-provenance", type=Path, required=True)
    args = parser.parse_args()
    dut = args.dut_vo.resolve()
    provenance_path = args.dut_provenance.resolve()
    provenance = json.loads(provenance_path.read_text())
    assert provenance["result"] == "PASS" and provenance["delivered_netlist_sha256"] == sha(dut)
    top = "afdx_stage2_mgmt_top"
    assert re.search(r"\bmodule\s+" + top + r"\b", dut.read_text(errors="replace"))
    assert REF.is_dir()
    libs = ("altera_primitives.v", "220model.v", "stratix_atoms.v")
    for name in libs:
        assert (REF / name).is_file()

    root = ROOT / "build/logs"
    i = 1
    while (root / f"mgmt_vo_{i:03d}").exists():
        i += 1
    run = root / f"mgmt_vo_{i:03d}"
    run.mkdir(parents=True)
    sources = list(FROZEN) + [ROOT / "rtl" / name for name in RTL]
    tb = ROOT / "sim/tb_stage2_mgmt_vo.sv"
    runner_files = [Path(__file__), ROOT / "scripts/generate_stage2_mgmt_golden.py",
                    ROOT / "scripts/generate_snmp_golden.py", ROOT / "scripts/frozen_frame_reference.py",
                    tb]
    for path in sources + runner_files:
        shutil.copy2(path, run / path.name)
    shutil.copy2(dut, run / f"{top}.vo")
    for name in libs:
        shutil.copy2(REF / name, run / name)
    golden = run / "golden"
    generated = generate(golden)
    cases = json.loads((golden / "cases.json").read_text())
    (run / "tx_expect.mem").write_text("".join(f"{int(case['expect_tx'])}\n" for case in cases), encoding="ascii")
    shutil.copy2(MS.parent / "modelsim.ini", run / "modelsim.ini")
    os.chmod(run / "modelsim.ini", 0o666)

    commands = ["onerror {quit -code 2 -force}", "vlib work", "vmap work work"]
    compile_names = list(libs) + [path.name for path in sources] + [f"{top}.vo", tb.name]
    for name in compile_names:
        sv = "-sv " if name.endswith(".sv") else ""
        commands.append(f"vlog {sv}+incdir+{{{run.as_posix()}}} {{{(run / name).as_posix()}}}")
    simtop = "tb_stage2_mgmt_vo"
    commands += [f"vopt -O5 -inlineFactor=100 work.{simtop} -o mgmt_vo_optimized",
                 "vsim -t 1ps -wlf waves.wlf work.mgmt_vo_optimized",
                 "run -all", "quit -code 0 -force"]
    (run / "run.do").write_text("\n".join(commands) + "\n", encoding="ascii")

    env = os.environ.copy()
    env.setdefault("MGLS_LICENSE_FILE", str(MS.parent / "LICENSE.TXT"))
    command = [str(MS / "vsim.exe"), "-batch", "-modelsimini", "modelsim.ini", "-l", "transcript.log", "-do", "do run.do"]
    source_inputs = sources + runner_files + [dut, provenance_path] + [REF / name for name in libs]
    summary = {"result": "RUNNING", "run": str(run), "started_utc": datetime.now(timezone.utc).isoformat(),
               "scope": "full 57-case management system clock regression against real EQ6 synthesis functional VO",
               "golden": generated, "modelsim_command": command,
               "dut_vo": str(dut), "dut_vo_sha256": sha(dut),
               "dut_export_provenance": str(provenance_path), "dut_export_provenance_sha256": sha(provenance_path),
               "RTL_DUT_compiled": False, "force_used": False, "vendor_models": {name: sha(REF / name) for name in libs},
               "inputs_sha256": {str(p): sha(p) for p in source_inputs}}
    (run / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    with (run / "console.log").open("wb") as log:
        process = subprocess.Popen(command, cwd=run, env=env, stdout=log, stderr=subprocess.STDOUT)
        summary["modelsim_pid"] = process.pid
        (run / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(f"MGMT_VO_RUN {run} PID {process.pid}", flush=True)
        code = process.wait(timeout=86400)

    transcript = (run / "transcript.log").read_text(errors="replace")
    passed = code == 0 and "MGMT_VO_RUN cases=57 tx_frames=47 tx_bytes=6484" in transcript and \
             "Errors: 0" in transcript and "** Fatal" not in transcript and "** Error" not in transcript
    error = None
    evidence = {}
    compared = 0
    if passed:
        try:
            cases = json.loads((golden / "cases.json").read_text())
            expected_wire = bytes(int(x, 16) for x in (golden / "expected_tx_wire.mem").read_text().split())
            actual = bytes(int(x, 16) for x in (run / "actual_tx.mem").read_text().split())
            events = list(csv.DictReader((run / "tx_events.csv").open(newline="")))
            inputs = {int(row["frame"]): row for row in csv.DictReader((run / "rx_events.csv").open(newline=""))}
            expected = [c for c in cases if c["expect_tx"]]
            assert generated["frames"] == 57 and len(cases) == 57
            assert len(expected) == 47 and len(events) == 47
            assert len(expected_wire) == 6484 and len(actual) == 6484
            offset = 0
            gaps = defaultdict(list)
            last = {}
            latencies = []
            for event, case in zip(events, expected):
                size = int(event["bytes"])
                frame = actual[offset:offset + size]
                offset += size
                golden_frame = expected_wire[case["tx_offset"]:case["tx_offset"] + case["tx_length"]]
                assert frame == golden_frame, f"wire mismatch for {case['name']}"
                assert size == case["tx_length"]
                assert int(event["end_cycle"]) - int(event["start_cycle"]) + 1 == size
                vlid = int.from_bytes(frame[12:14], "big")
                start = int(event["start_cycle"])
                if vlid in last:
                    gaps[vlid].append(start - last[vlid])
                last[vlid] = start
                if case["id"] in inputs:
                    latencies.append((start - int(inputs[case["id"]]["start_cycle"])) * 8)
                compared += 1
            assert offset == len(actual) == len(expected_wire)
            assert gaps[BUSINESS_VL] and min(gaps[BUSINESS_VL]) >= 125000
            for vlid, intervals in gaps.items():
                assert min(intervals) >= 125000, f"BAG violation on {vlid:04x}: {min(intervals)}"
            assert latencies
            evidence = {"cases": len(cases), "frames_compared": compared,
                        "tx_wire_bytes_compared": len(actual), "bag_cycles": {
                            hex(vlid): {"min": min(values), "max": max(values)} for vlid, values in gaps.items()},
                        "gmii_input_first_byte_to_output_first_byte_ns": {
                            "min": min(latencies), "max": max(latencies)},
                        "full_clock_period_ns": 8, "actual_vendor_primitive_models": True}
        except (AssertionError, KeyError, IndexError, ValueError) as exc:
            passed = False
            error = f"independent Golden check failed: {exc}"
    summary.update(result="PASS" if passed else "FAIL", exit_code=code, frames_compared=compared,
                   error=error, evidence=evidence, completed_utc=datetime.now(timezone.utc).isoformat(),
                   artifacts={p.name: sha(p) for p in run.iterdir() if p.is_file() and p.name != "summary.json"})
    (run / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(transcript[-1800:])
    print(json.dumps({"result": summary["result"], "run": str(run), "frames": compared, "error": error}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
