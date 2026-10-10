from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
MS = Path(r"D:\FPGA\Modlesim20.4\ModelSim20.4\win64")
ELINX_LIB = Path(r"D:\FPGA\eLinx3.0\Simulation\elinx_lib")
LIBS = [ELINX_LIB / n for n in ("altera_primitives.v", "220model.v", "stratix_atoms.v")]
TB = ROOT / "sim" / "tb_b1_netlist_loopback.sv"
GOLDEN_GENERATOR = ROOT / "scripts" / "generate_single_vl_golden.py"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run B1 ModelSim against an actual eLinx-exported functional netlist.")
    parser.add_argument("netlist", type=Path, help="eLinx-generated afdx_network_tx_top functional .vo")
    parser.add_argument("--suite", choices=("basic", "full"), default="basic")
    parser.add_argument("--functional-zero-delay", action="store_true", help="ModelSim documented functional mode: ignore specify/structural delays; same netlist/libraries and cycle/data assertions, never timing evidence")
    parser.add_argument("--assertion-only", action="store_true", help="Performance diagnostic: normal netlist optimization, all TB assertions/CSV active; waveform variable visibility off")
    args = parser.parse_args()
    testbench = ROOT / "sim" / ("tb_b1_netlist_full.sv" if args.suite == "full" else "tb_b1_netlist_loopback.sv")
    test_top = testbench.stem
    pass_marker = "B1_POST_SYNTH_NETLIST_FULL = PASS" if args.suite == "full" else "B1_POST_SYNTH_NETLIST_FUNCTIONAL = PASS"
    netlist = args.netlist.resolve(strict=True)
    if netlist.suffix.lower() != ".vo":
        raise SystemExit("The DUT must be an eLinx-exported .vo, not RTL")
    content = netlist.read_text(errors="replace")
    active_content = re.sub(r"/\*.*?\*/|//[^\n]*", "", content, flags=re.S)
    if "$sdf_annotate" in active_content:
        raise SystemExit("This netlist requests SDF annotation. Preserve it and review the post-route/SDF scope before running; current runner is functional-only.")
    if not re.search(r"\bmodule\s+afdx_network_tx_top\b", content):
        raise SystemExit("The .vo does not declare the expected top afdx_network_tx_top")
    for path in LIBS + [testbench, GOLDEN_GENERATOR]:
        if not path.is_file():
            raise FileNotFoundError(path)

    i = 1
    while (ROOT / "runs" / f"netlist_{i:03d}").exists():
        i += 1
    run = ROOT / "runs" / f"netlist_{i:03d}"
    run.mkdir()
    net_snapshot = run / "afdx_network_tx_top.vo"
    shutil.copy2(netlist, net_snapshot)
    tb_snapshot = run / testbench.name
    shutil.copy2(testbench, tb_snapshot)
    lib_snapshots = []
    for lib in LIBS:
        target = run / lib.name
        shutil.copy2(lib, target)
        lib_snapshots.append(target)
    golden_dir = run / "golden"
    generated = subprocess.run([sys.executable, str(GOLDEN_GENERATOR), "--out", str(golden_dir)], capture_output=True, text=True, timeout=60)
    (run / "golden_generation.log").write_text(generated.stdout + generated.stderr, encoding="utf-8")
    if generated.returncode:
        print(generated.stdout + generated.stderr)
        return 1

    shutil.copy2(MS.parent / "modelsim.ini", run / "modelsim.ini")
    os.chmod(run / "modelsim.ini", 0o666)
    do_lines = ["onerror {quit -code 2 -force}", "onbreak {resume}", "vlib work", "vmap work work"]
    for source in lib_snapshots + [net_snapshot, tb_snapshot]:
        options = "-sv +define+DUT_IS_NETLIST " if source.suffix.lower() == ".sv" else ""
        do_lines.append(f"vlog {options}+incdir+{{{run.as_posix()}}} -work work {{{source.as_posix()}}}")
    # Use normal ModelSim optimization and record observed external signals.
    # Logging all flattened primitive internals would add millions of irrelevant
    # waveform events during the mandatory real BAG intervals of the SN wrap.
    observed = ["reset", "gmii_txd", "gmii_tx_en", "gmii_tx_er", "gmii_rxd", "gmii_rx_dv", "gmii_rx_er", "msg_done", "msg_error", "error_code", "late_count", "rx_data", "rx_valid", "rx_ready", "rx_sop", "rx_eop", "rx_length", "payload_data", "payload_valid", "payload_ready", "payload_last", "payload_abort"]
    if args.suite == "basic":
        observed.append("clk")
    functional_options = "+nospecify +delay_mode_zero " if args.functional_zero_delay else ""
    accessibility = "" if args.assertion_only else f"+acc=nr+{test_top} "
    do_lines += [f"vopt -O5 -inlineFactor=100 {functional_options}{accessibility}work.{test_top} -o b1_netlist_optimized", "vsim -t 1ps -onfinish stop -wlf waves.wlf work.b1_netlist_optimized"]
    if not args.assertion_only:
        do_lines += ["log " + " ".join(f"/{test_top}/{n}" for n in observed)]
    do_lines += ["run -all", "quit -code 0 -force"]
    (run / "run.do").write_text("\n".join(do_lines) + "\n", encoding="utf-8")
    version = subprocess.check_output([str(MS / "vsim.exe"), "-version"], stderr=subprocess.STDOUT).decode(errors="replace").strip()
    env = os.environ.copy()
    env["MGLS_LICENSE_FILE"] = str(MS.parent / "LICENSE.TXT")
    command = [str(MS / "vsim.exe"), "-batch", "-modelsimini", "modelsim.ini", "-l", "transcript.log", "-do", "do run.do"]
    result = subprocess.run(command, cwd=run, env=env, capture_output=True, timeout=43200 if args.suite == "full" else 900)
    (run / "console.log").write_bytes(result.stdout + result.stderr)
    transcript = (run / "transcript.log").read_text(errors="replace") if (run / "transcript.log").exists() else ""
    passed = result.returncode == 0 and pass_marker in transcript and "Errors: 0" in transcript and "** Error" not in transcript and "** Fatal" not in transcript
    provenance = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "result": "PASS" if passed else "FAIL",
        "model_sim_version": version,
        "command": command,
        "working_directory": str(run),
        "exit_code": result.returncode,
        "scope": "Actual eLinx-generated top-level .vo is the DUT; no B0/B1 RTL source compiled; independent Python Golden controls GMII TX bytes/FCS and MAC RX payload; tests padding boundaries, maximum payload, malformed partial-frame cleanup, BAG, reset and recovery",
        "netlist_input": {"path": str(netlist), "sha256": sha(netlist), "snapshot_sha256": sha(net_snapshot)},
        "suite": args.suite,
        "functional_zero_delay": args.functional_zero_delay,
        "assertion_only": args.assertion_only,
        "testbench": {"path": str(testbench), "sha256": sha(testbench), "snapshot_sha256": sha(tb_snapshot)},
        "primitive_libraries": [{"path": str(src), "sha256": sha(src)} for src in LIBS],
        "golden_manifest_sha256": sha(golden_dir / "manifest.json"),
        "timing_or_sdf": "No SDF. +nospecify/+delay_mode_zero functional simulation, not timing verification" if args.functional_zero_delay else "No SDF; primitive default behavior; functional netlist simulation only",
    }
    (run / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    (run / "summary.json").write_text(json.dumps({"result": "PASS" if passed else "FAIL", "suite": args.suite, "functional_zero_delay": args.functional_zero_delay, "run": str(run), "model_sim_version": version, "exit_code": result.returncode}, indent=2), encoding="utf-8")
    print(transcript[-5000:])
    print("B1_NETLIST_RUN", run, "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
