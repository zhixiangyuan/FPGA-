from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import argparse
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
B0 = Path(r"D:\FPGA\captain_integration\stage5B0_selfmac_20261010")
MS = Path(r"D:\FPGA\Modlesim20.4\ModelSim20.4\win64")
SOURCES = [
    B0 / "deps" / "afdx_byte_fifo.v",
    B0 / "rtl" / "mac_crc32_byte.v",
    B0 / "rtl" / "mac_frame_store.v",
    B0 / "rtl" / "mac_gmii_tx.v",
    B0 / "rtl" / "mac_gmii_rx.v",
    B0 / "rtl" / "mac_gmii_core.v",
] + sorted((ROOT / "rtl").glob("*.v")) + [ROOT / "sim" / "tb_b1_netlist_loopback.sv"]
GOLDEN = ROOT / "scripts" / "generate_single_vl_golden.py"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument('--full-tb-quick',action='store_true')
    args=parser.parse_args()
    sources=SOURCES[:-1]+[ROOT/'sim'/'tb_b1_netlist_full.sv'] if args.full_tb_quick else SOURCES
    top='tb_b1_netlist_full' if args.full_tb_quick else 'tb_b1_netlist_loopback'
    marker='B1_FULL_TB_QUICK_RTL = PASS' if args.full_tb_quick else 'B1_125M_RTL_GMII_FUNCTIONAL = PASS'
    i = 1
    while (ROOT / "runs" / f"clk125_{i:03d}").exists():
        i += 1
    run = ROOT / "runs" / f"clk125_{i:03d}"
    run.mkdir()
    source_dir = run / "src"
    source_dir.mkdir()
    snapshots = []
    for original in sources:
        if not original.is_file():
            raise FileNotFoundError(original)
        target = source_dir / original.name
        shutil.copy2(original, target)
        snapshots.append(target)
    golden_dir = run / "golden"
    generated = subprocess.run([sys.executable, str(GOLDEN), "--out", str(golden_dir)], capture_output=True, text=True, timeout=60)
    (run / "golden_generation.log").write_text(generated.stdout + generated.stderr, encoding="utf-8")
    if generated.returncode:
        print(generated.stdout + generated.stderr)
        return 1
    shutil.copy2(MS.parent / "modelsim.ini", run / "modelsim.ini")
    os.chmod(run / "modelsim.ini", 0o666)
    do_lines = ["onerror {quit -code 2 -force}", "onbreak {resume}", "vlib work", "vmap work work"]
    do_lines.extend(f"vlog -sv {'+define+QUICK_PRESSURE_ONLY ' if args.full_tb_quick else ''}-work work {{{p.as_posix()}}}" for p in snapshots)
    do_lines.extend([f"vsim -onfinish stop -voptargs=+acc -wlf waves.wlf work.{top}", "log -r /*", "run -all", "quit -code 0 -force"])
    (run / "run.do").write_text("\n".join(do_lines) + "\n", encoding="utf-8")
    version = subprocess.check_output([str(MS / "vsim.exe"), "-version"], stderr=subprocess.STDOUT).decode(errors="replace").strip()
    env = os.environ.copy()
    env["MGLS_LICENSE_FILE"] = str(MS.parent / "LICENSE.TXT")
    command = [str(MS / "vsim.exe"), "-batch", "-modelsimini", "modelsim.ini", "-l", "transcript.log", "-do", "do run.do"]
    result = subprocess.run(command, cwd=run, env=env, capture_output=True, timeout=300)
    (run / "console.log").write_bytes(result.stdout + result.stderr)
    transcript = (run / "transcript.log").read_text(errors="replace") if (run / "transcript.log").exists() else ""
    passed = result.returncode == 0 and marker in transcript and "Errors: 0" in transcript and "** Error" not in transcript and "** Fatal" not in transcript
    (run / "provenance.json").write_text(json.dumps({
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "result": "PASS" if passed else "FAIL",
        "model_sim_version": version,
        "command": command,
        "scope": "125MHz-equivalent 8ns RTL simulation of B1 and real B0 MAC; BAG=125000 cycles for 1ms; this is digital functional validation, not physical timing evidence",
        "source_inputs": [{"original": str(src), "original_sha256": sha(src), "snapshot": str(snap), "snapshot_sha256": sha(snap)} for src, snap in zip(sources, snapshots)],
        "mode": "New full-suite TB quick pressure validation on RTL; not netlist/SN-wrap evidence" if args.full_tb_quick else "125MHz RTL regression",
        "golden_manifest_sha256": sha(golden_dir / "manifest.json"),
        "exit_code": result.returncode,
    }, indent=2), encoding="utf-8")
    (run / "summary.json").write_text(json.dumps({"result": "PASS" if passed else "FAIL", "run": str(run), "model_sim_version": version}, indent=2), encoding="utf-8")
    print(transcript[-4500:])
    print("B1_125M_RTL_RUN", run, "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
