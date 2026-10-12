"""Run one full ModelSim suite against archived or newly exported real V1 VO."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = Path(os.environ.get("AFDX_BUILD_ROOT", ROOT / "build"))
EVIDENCE_ROOT = Path(os.environ.get("AFDX_V1_EVIDENCE_ROOT", ROOT / "evidence"))
MODELSIM_BIN = Path(os.environ.get("MODELSIM_BIN", r"D:\FPGA\Modlesim20.4\ModelSim20.4\win64"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=EVIDENCE_ROOT / "netlist_001",
                        help="immutable archived netlist_001 run containing the VO, libraries, TB and Golden")
    parser.add_argument("--dut-vo", type=Path,
                        help="optional real functional VO exported from the candidate eLinx project")
    parser.add_argument("--dut-provenance", type=Path,
                        help="optional provenance JSON for --dut-vo")
    parser.add_argument("--timeout-seconds", type=int, default=86400)
    args = parser.parse_args()

    reference = args.reference.resolve()
    if not reference.is_dir():
        raise FileNotFoundError(f"Archived real-VO run not found: {reference}")
    reference_summary = json.loads((reference / "summary.json").read_text(encoding="utf-8"))
    reference_provenance = json.loads((reference / "provenance.json").read_text(encoding="utf-8"))
    if reference_summary.get("result") != "PASS" or reference_summary.get("exit_code") != 0:
        raise RuntimeError("The archived reference VO run is not a verified PASS")
    if reference_provenance.get("RTL_DUT_compiled") or reference_provenance.get("force_used"):
        raise RuntimeError("Reference provenance does not describe a real VO-only test")
    for row in reference_summary.get("sources", []):
        snapshot = reference / Path(row["path"]).name
        if not snapshot.is_file() or sha(snapshot) != row["snapshot_sha256"]:
            raise RuntimeError(f"Archived input hash mismatch: {snapshot}")

    golden = reference / "golden"
    golden_manifest = golden / "sha256.json"
    for name, digest in json.loads(golden_manifest.read_text(encoding="utf-8")).items():
        if sha(golden / name) != digest:
            raise RuntimeError(f"Archived Golden hash mismatch: {name}")

    dut = args.dut_vo.resolve() if args.dut_vo else reference / "AFDX_top.vo"
    if not dut.is_file() or "module AFDX_top" not in dut.read_text(encoding="utf-8", errors="replace"):
        raise RuntimeError(f"DUT is not a functional AFDX_top Verilog netlist: {dut}")
    if args.dut_provenance:
        provenance_path = args.dut_provenance.resolve()
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        if provenance.get("result") != "PASS" or provenance.get("delivered_netlist_sha256") != sha(dut):
            raise RuntimeError("Candidate VO does not match its passing export provenance")
    else:
        provenance_path = None

    run_root = BUILD_ROOT / "logs"
    run_root.mkdir(parents=True, exist_ok=True)
    lock = run_root / "V1_NETLIST_RUNNING.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(f"A netlist run already holds {lock}; do not start a duplicate") from exc

    index = 1
    while (run_root / f"netlist_{index:03d}").exists():
        index += 1
    run = run_root / f"netlist_{index:03d}"
    run.mkdir()
    os.write(fd, json.dumps({"runner_pid": os.getpid(), "run": str(run), "started_utc": now()}).encode())
    os.close(fd)

    summary = {"result": "PREPARING", "run": str(run), "started_utc": now(), "runner_pid": os.getpid()}
    write_json(run / "summary.json", summary)
    try:
        names = ("AFDX_top.vo", "altera_primitives.v", "220model.v", "stratix_atoms.v",
                 "tb_v1_netlist.sv", "v1_netlist_observer.vh")
        for name in names:
            source = dut if name == "AFDX_top.vo" else reference / name
            shutil.copy2(source, run / name)
        shutil.copytree(golden, run / "golden")
        shutil.copy2(MODELSIM_BIN.parent / "modelsim.ini", run / "modelsim.ini")
        os.chmod(run / "modelsim.ini", 0o666)

        top = "tb_v1_netlist"
        do = ["onerror {quit -code 2 -force}", "vlib work", "vmap work work"]
        compile_names = ("altera_primitives.v", "220model.v", "stratix_atoms.v", "AFDX_top.vo", "tb_v1_netlist.sv")
        for name in compile_names:
            sv = "-sv " if name.endswith(".sv") else ""
            do.append(f"vlog {sv}+incdir+{{{run.as_posix()}}} {{{(run / name).as_posix()}}}")
        do.extend((f"vopt -O5 -inlineFactor=100 +acc=nr+{top} work.{top} -o v1_real_optimized",
                   f"vsim -t 1ps -onfinish stop -wlf waves.wlf work.v1_real_optimized",
                   "log /tb_v1_netlist/reset /tb_v1_netlist/rx_data /tb_v1_netlist/rx_valid /tb_v1_netlist/tx_data /tb_v1_netlist/tx_valid",
                   "run -all", "quit -code 0 -force"))
        (run / "run.do").write_text("\n".join(do) + "\n", encoding="utf-8")

        env = os.environ.copy()
        env.setdefault("MGLS_LICENSE_FILE", str(MODELSIM_BIN.parent / "LICENSE.TXT"))
        command = [str(MODELSIM_BIN / "vsim.exe"), "-batch", "-modelsimini", "modelsim.ini",
                   "-l", "transcript.log", "-do", "do run.do"]
        summary.update({"result": "RUNNING", "modelsim_command": command})
        write_json(run / "summary.json", summary)
        proof = {
            "command": command,
            "DUT": "AFDX_top.vo",
            "dut_sha256": sha(run / "AFDX_top.vo"),
            "dut_source": str(dut),
            "dut_export_provenance": str(provenance_path) if provenance_path else "archived PASS netlist_001 snapshot",
            "dut_export_provenance_sha256": sha(provenance_path) if provenance_path else None,
            "RTL_DUT_compiled": False,
            "force_used": False,
            "actual_vendor_primitive_models": True,
            "BAG_cycles": 125000,
            "SN_wrap_frames": 256,
            "reference_run": str(reference),
            "reference_summary_sha256": sha(reference / "summary.json"),
            "golden_manifest_sha256": sha(run / "golden" / "sha256.json"),
            "inputs_sha256": {name: sha(run / name) for name in names},
            "POST_SYNTH_TIMING": "NOT VERIFIED",
            "EQ6_NATIVE_NETLIST_EQUIVALENCE": "NOT VERIFIED",
        }
        write_json(run / "provenance.json", proof)
        with (run / "console.log").open("wb") as console:
            process = subprocess.Popen(command, cwd=run, env=env, stdout=console, stderr=subprocess.STDOUT)
            summary.update({"modelsim_pid": process.pid, "started_utc": now()})
            write_json(run / "summary.json", summary)
            print(f"V1_REAL_NETLIST_RUN {run} PID {process.pid}", flush=True)
            try:
                exit_code = process.wait(timeout=args.timeout_seconds)
            except subprocess.TimeoutExpired:
                summary.update({"result": "TIMEOUT", "completed_utc": now()})
                write_json(run / "summary.json", summary)
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
                raise

        transcript = (run / "transcript.log").read_text(encoding="utf-8", errors="replace")
        expected = ("V1_REAL_NETLIST = PASS", "V1_NETLIST_PRESSURE = PASS",
                    "V1_NETLIST_PARTIAL_RESET = PASS", "Errors: 0")
        passed = exit_code == 0 and all(token in transcript for token in expected)
        passed = passed and "** Fatal" not in transcript and "** Error" not in transcript
        summary.update({"result": "PASS" if passed else "FAIL", "exit_code": exit_code, "completed_utc": now()})
        summary["artifact_hashes"] = {p.name: sha(p) for p in run.iterdir() if p.is_file() and p.name != "summary.json"}
        write_json(run / "summary.json", summary)
        print(transcript[-2500:])
        print(f"V1_REAL_NETLIST_RESULT {summary['result']} {run}", flush=True)
        return 0 if passed else 1
    except Exception as exc:
        if summary.get("result") != "TIMEOUT":
            summary.update({"result": "FAIL", "exception": repr(exc), "completed_utc": now()})
            write_json(run / "summary.json", summary)
        raise
    finally:
        if lock.exists():
            lock.replace(run / "runner_closed.lock")


if __name__ == "__main__":
    raise SystemExit(main())
