"""Run the real B1/B0 GMII -> B2 candidate-parser protocol loop."""

from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
MS = Path(r"D:\FPGA\Modlesim20.4\ModelSim20.4\win64")
B0 = BASE / "stage5B0_selfmac_20261010" / "rtl"
B1 = BASE / "stage5B1_single_vl_20261010" / "rtl"
BYTE = BASE / "stage3B2_20261008" / "rtl" / "afdx_byte_fifo.v"
SOURCES = [
    BYTE,
    *[B0 / name for name in ("mac_crc32_byte.v", "mac_frame_store.v", "mac_gmii_tx.v",
                               "mac_gmii_rx.v", "mac_gmii_core.v")],
    *[B1 / name for name in ("afdx_ipv4_checksum.v", "afdx_bag_gate.v",
                               "afdx_single_vl_tx.v", "afdx_network_tx_top.v")],
    ROOT / "rtl" / "afdx_single_vl_rx_candidate.v",
    ROOT / "rtl" / "afdx_single_vl_sn_gate.v",
    ROOT / "rtl" / "afdx_protocol_rx_top.v",
    ROOT / "sim" / "tb_b2_full_protocol.sv",
]


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    index = 1
    while (ROOT / "runs" / f"full_{index:03d}").exists():
        index += 1
    run = ROOT / "runs" / f"full_{index:03d}"
    run.mkdir(parents=True)
    snapshots = []
    for source in SOURCES:
        target = run / source.name
        shutil.copy2(source, target)
        snapshots.append(target)
    golden = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate_b2_full_golden.py"),
         "--out", str(run / "golden")], capture_output=True, text=True, timeout=60)
    (run / "golden_generation.log").write_text(golden.stdout + golden.stderr, encoding="utf-8")
    if golden.returncode:
        print(golden.stdout + golden.stderr)
        return golden.returncode
    shutil.copy2(MS.parent / "modelsim.ini", run / "modelsim.ini")
    os.chmod(run / "modelsim.ini", 0o666)
    do = ["onerror {quit -code 2 -force}", "vlib work", "vmap work work"]
    do += [f"vlog -sv +incdir+{{{run.as_posix()}}} {{{p.as_posix()}}}" for p in snapshots]
    top = "tb_b2_full_protocol"
    do += [f"vopt -O5 -inlineFactor=100 +acc=nr+{top} work.{top} -o b2_loop_optimized",
           "vsim -t 1ps -onfinish stop -wlf waves.wlf work.b2_loop_optimized"]
    observed = ("reset", "psn", "psn_valid", "sn_accepted", "sn_rejected", "sn_reset_control", "gmii_txd", "gmii_tx_en", "gmii_rxd", "gmii_rx_dv",
                "app_data", "app_valid", "app_ready", "app_sop", "app_eop",
                "candidate_accepted", "candidate_rejected", "candidate_reject_reason",
                "mac_rx_accepted", "mac_rx_dropped", "msg_done", "late_count")
    do += ["log " + " ".join(f"/{top}/{signal}" for signal in observed),
           "run -all", "quit -code 0 -force"]
    (run / "run.do").write_text("\n".join(do) + "\n", encoding="utf-8")
    env = os.environ.copy()
    env["MGLS_LICENSE_FILE"] = str(MS.parent / "LICENSE.TXT")
    command = [str(MS / "vsim.exe"), "-batch", "-modelsimini", "modelsim.ini",
               "-l", "transcript.log", "-do", "do run.do"]
    result = subprocess.run(command, cwd=run, env=env, capture_output=True, timeout=3600)
    (run / "console.log").write_bytes(result.stdout + result.stderr)
    transcript = (run / "transcript.log").read_text(errors="replace")
    marker = "B2_FULL_SN_PROTOCOL = PASS"
    passed = result.returncode == 0 and marker in transcript and "B2_SN_CAPACITY_RESET = PASS" in transcript and "Errors: 0" in transcript and \
        "** Fatal" not in transcript and "** Error" not in transcript
    summary = {
        "result": "PASS" if passed else "FAIL", "suite": "full_sn_real_protocol_loop",
        "sn_policy": "APPROVED_XAPP_SINGLE_VL_PROFILE",
        "exit_code": result.returncode, "run": str(run),
        "sources": [{"path": str(src), "sha256": digest(src),
                     "snapshot_sha256": digest(snapshot)}
                    for src, snapshot in zip(SOURCES, snapshots)],
        "golden_sha256": digest(run / "golden" / "sha256.json"),
    }
    (run / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(transcript[-5000:])
    print("B2_LOOP_RUN", run, summary["result"])
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
