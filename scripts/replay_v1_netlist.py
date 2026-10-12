"""Replay the sealed real-VO evidence from an external, locally licensed archive."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = Path(os.environ.get("AFDX_BUILD_ROOT", ROOT / "build"))
DEFAULT_EVIDENCE = Path(os.environ.get("AFDX_V1_EVIDENCE_ROOT", ROOT / "evidence"))
MODELSIM_BIN = Path(os.environ.get("MODELSIM_BIN", r"D:\FPGA\Modlesim20.4\ModelSim20.4\win64"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=DEFAULT_EVIDENCE / "netlist_001",
                        help="archived netlist_001 evidence directory")
    parser.add_argument("--dut-vo", type=Path,
                        help="optional real VO exported from the prepared candidate eLinx project")
    parser.add_argument("--dut-provenance", type=Path,
                        help="passing export provenance JSON required with --dut-vo")
    parser.add_argument("--load-only", action="store_true",
                        help="compile and load the real VO, then run 0 ns")
    args = parser.parse_args()
    source = args.reference.resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Real-VO evidence directory not found: {source}; restore the offline V1.0 archive first")

    reference_summary = json.loads((source / "summary.json").read_text(encoding="utf-8"))
    if reference_summary.get("result") != "PASS" or reference_summary.get("exit_code") != 0:
        raise RuntimeError("Reference netlist_001 is not the recorded PASS run")
    for row in reference_summary.get("sources", []):
        snapshot = source / Path(row["path"]).name
        if sha(snapshot) != row["snapshot_sha256"]:
            raise RuntimeError(f"Archived source hash mismatch: {snapshot.name}")
    golden = source / "golden"
    for name, digest in json.loads((golden / "sha256.json").read_text(encoding="utf-8")).items():
        if sha(golden / name) != digest:
            raise RuntimeError(f"Golden hash mismatch: {name}")

    dut = args.dut_vo.resolve() if args.dut_vo else source / "AFDX_top.vo"
    if not dut.is_file() or "module AFDX_top" not in dut.read_text(encoding="utf-8", errors="replace"):
        raise RuntimeError(f"DUT is not an AFDX_top Verilog netlist: {dut}")
    dut_provenance = None
    if args.dut_vo:
        if not args.dut_provenance:
            raise RuntimeError("--dut-provenance is required with --dut-vo")
        dut_provenance = args.dut_provenance.resolve()
        proof = json.loads(dut_provenance.read_text(encoding="utf-8"))
        if proof.get("result") != "PASS" or proof.get("delivered_netlist_sha256") != sha(dut):
            raise RuntimeError("Candidate VO hash does not match its successful export provenance")

    run_root = BUILD_ROOT / "logs"
    run_root.mkdir(parents=True, exist_ok=True)
    index = 1
    while (run_root / f"replay_{index:03d}").exists():
        index += 1
    run = run_root / f"replay_{index:03d}"
    run.mkdir()

    inputs = ("AFDX_top.vo", "altera_primitives.v", "220model.v", "stratix_atoms.v",
              "tb_v1_netlist.sv", "v1_netlist_observer.vh")
    for name in inputs:
        shutil.copy2(dut if name == "AFDX_top.vo" else source / name, run / name)
    shutil.copytree(golden, run / "golden")
    shutil.copy2(MODELSIM_BIN.parent / "modelsim.ini", run / "modelsim.ini")
    os.chmod(run / "modelsim.ini", 0o666)

    do = ["onerror {quit -code 2 -force}", "vlib work", "vmap work work"]
    for name in ("altera_primitives.v", "220model.v", "stratix_atoms.v", "AFDX_top.vo", "tb_v1_netlist.sv"):
        sv = "-sv " if name.endswith(".sv") else ""
        do.append(f"vlog {sv}+incdir+{{{run.as_posix()}}} {{{(run / name).as_posix()}}}")
    do.extend(("vopt -O5 -inlineFactor=100 +acc=nr+tb_v1_netlist work.tb_v1_netlist -o replay_optimized",
               "vsim -t 1ps -onfinish stop -wlf waves.wlf work.replay_optimized",
               "log /tb_v1_netlist/reset /tb_v1_netlist/rx_data /tb_v1_netlist/rx_valid /tb_v1_netlist/tx_data /tb_v1_netlist/tx_valid",
               "run 0ns" if args.load_only else "run -all",
               "quit -code 0 -force"))
    (run / "run.do").write_text("\n".join(do) + "\n", encoding="utf-8")

    env = os.environ.copy()
    env.setdefault("MGLS_LICENSE_FILE", str(MODELSIM_BIN.parent / "LICENSE.TXT"))
    command = [str(MODELSIM_BIN / "vsim.exe"), "-batch", "-modelsimini", "modelsim.ini",
               "-l", "transcript.log", "-do", "do run.do"]
    with (run / "console.log").open("wb") as log:
        result = subprocess.run(command, cwd=run, env=env, stdout=log,
                                stderr=subprocess.STDOUT, timeout=86400)
    transcript = (run / "transcript.log").read_text(errors="replace")
    passed = (result.returncode == 0 and "Errors: 0" in transcript
              and "** Error" not in transcript and "** Fatal" not in transcript
              and (args.load_only or "V1_REAL_NETLIST = PASS" in transcript))
    summary = {
        "result": "PASS" if passed else "FAIL",
        "scope": "real VO compile/load and 0 ns" if args.load_only else "full real VO replay",
        "full_clocked_suite_executed": not args.load_only,
        "exit_code": result.returncode,
        "reference_evidence": str(source),
        "dut_source": str(dut),
        "dut_sha256": sha(dut),
        "dut_export_provenance": str(dut_provenance) if dut_provenance else "archived PASS netlist_001 snapshot",
        "dut_export_provenance_sha256": sha(dut_provenance) if dut_provenance else None,
        "compile_list_contains_RTL_DUT": False,
        "source_hashes": {name: sha(run / name) for name in inputs},
        "golden_sha256": sha(run / "golden" / "sha256.json"),
        "command": command,
    }
    (run / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
