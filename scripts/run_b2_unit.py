"""Run a numbered ModelSim candidate-parser test with immutable snapshots."""

from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MS = Path(r"D:\FPGA\Modlesim20.4\ModelSim20.4\win64")
PARSER = ROOT / "rtl" / "afdx_single_vl_rx_candidate.v"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=("unit", "pressure"), default="unit")
    args = parser.parse_args()
    test_top = "tb_b2_rx_candidate" if args.suite == "unit" else "tb_b2_rx_pressure"
    marker = "B2_RX_PARSER_UNIT = PASS" if args.suite == "unit" else "B2_RX_PRESSURE_RESET = PASS"
    sources = [PARSER, ROOT / "sim" / (test_top + ".sv")]
    index = 1
    while (ROOT / "runs" / f"{args.suite}_{index:03d}").exists():
        index += 1
    run = ROOT / "runs" / f"{args.suite}_{index:03d}"
    run.mkdir(parents=True)
    snapshots = []
    for source in sources:
        target = run / source.name
        shutil.copy2(source, target)
        snapshots.append(target)
    golden = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate_b2_golden.py"),
         "--out", str(run / "golden")], capture_output=True, text=True, timeout=60)
    (run / "golden_generation.log").write_text(golden.stdout + golden.stderr, encoding="utf-8")
    if golden.returncode:
        print(golden.stdout + golden.stderr)
        return golden.returncode
    shutil.copy2(MS.parent / "modelsim.ini", run / "modelsim.ini")
    os.chmod(run / "modelsim.ini", 0o666)
    do = ["onerror {quit -code 2 -force}", "vlib work", "vmap work work"]
    do += [f"vlog -sv +incdir+{{{run.as_posix()}}} {{{p.as_posix()}}}" for p in snapshots]
    observed = ("clk", "in_valid", "in_data", "in_ready", "payload_valid", "payload_data",
                "payload_ready", "candidate_accepted", "candidate_rejected", "reject_reason")
    do += [f"vopt +acc=nr+{test_top} work.{test_top} -o b2_unit_optimized",
           "vsim -t 1ps -onfinish stop -wlf waves.wlf work.b2_unit_optimized",
           "log " + " ".join(f"/{test_top}/{signal}" for signal in observed),
           "run -all", "quit -code 0 -force"]
    (run / "run.do").write_text("\n".join(do) + "\n", encoding="utf-8")
    env = os.environ.copy()
    env["MGLS_LICENSE_FILE"] = str(MS.parent / "LICENSE.TXT")
    command = [str(MS / "vsim.exe"), "-batch", "-modelsimini", "modelsim.ini",
               "-l", "transcript.log", "-do", "do run.do"]
    result = subprocess.run(command, cwd=run, env=env, capture_output=True, timeout=600)
    (run / "console.log").write_bytes(result.stdout + result.stderr)
    transcript = (run / "transcript.log").read_text(errors="replace")
    passed = result.returncode == 0 and marker in transcript and \
        "Errors: 0" in transcript and "** Fatal" not in transcript and "** Error" not in transcript
    summary = {
        "result": "PASS" if passed else "FAIL", "suite": args.suite,
        "sn_policy": "UNCHECKED; awaiting captain approval",
        "exit_code": result.returncode, "run": str(run),
        "sources": [{"path": str(src), "sha256": digest(src),
                     "snapshot_sha256": digest(snapshot)}
                    for src, snapshot in zip(sources, snapshots)],
        "golden_sha256": digest(run / "golden" / "sha256.json"),
    }
    (run / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(transcript[-4000:])
    print("B2_UNIT_RUN", run, summary["result"])
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
