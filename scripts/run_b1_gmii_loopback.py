from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
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
] + sorted((ROOT / "rtl").glob("*.v")) + [ROOT / "sim" / "tb_b1_gmii_loopback.sv"]
GOLDEN_GENERATOR = ROOT / "scripts" / "generate_single_vl_golden.py"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def next_run() -> Path:
    i = 1
    while (ROOT / "runs" / f"gmii_{i:03d}").exists():
        i += 1
    run = ROOT / "runs" / f"gmii_{i:03d}"
    run.mkdir(parents=True)
    return run


def main() -> int:
    for path in SOURCES + [GOLDEN_GENERATOR]:
        if not path.is_file():
            raise FileNotFoundError(path)

    run = next_run()
    src_dir = run / "src"
    src_dir.mkdir()
    snapshots = []
    for src in SOURCES:
        target = src_dir / src.name
        shutil.copy2(src, target)
        snapshots.append(target)
    golden = run / "golden"
    generated = subprocess.run(
        [sys.executable, str(GOLDEN_GENERATOR), "--out", str(golden)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    (run / "golden_generation.log").write_text(generated.stdout + generated.stderr, encoding="utf-8")
    if generated.returncode:
        print(generated.stdout + generated.stderr)
        raise SystemExit("Golden generation failed")

    shutil.copy2(MS.parent / "modelsim.ini", run / "modelsim.ini")
    os.chmod(run / "modelsim.ini", 0o666)
    lines = [
        "onerror {quit -code 2 -force}",
        "onbreak {resume}",
        "vlib work",
        "vmap work work",
    ]
    lines.extend(f"vlog -sv -work work {{{p.as_posix()}}}" for p in snapshots)
    lines.extend([
        "vsim -onfinish stop -voptargs=+acc -wlf waves.wlf work.tb_b1_gmii_loopback",
        "log -r /*",
        "run -all",
        "quit -code 0 -force",
    ])
    (run / "run.do").write_text("\n".join(lines) + "\n", encoding="utf-8")
    version = subprocess.check_output([str(MS / "vsim.exe"), "-version"], stderr=subprocess.STDOUT).decode(errors="replace").strip()
    env = os.environ.copy()
    env["MGLS_LICENSE_FILE"] = str(MS.parent / "LICENSE.TXT")
    command = [str(MS / "vsim.exe"), "-batch", "-modelsimini", "modelsim.ini", "-l", "transcript.log", "-do", "do run.do"]
    result = subprocess.run(command, cwd=run, env=env, capture_output=True, timeout=300)
    (run / "console.log").write_bytes(result.stdout + result.stderr)
    transcript = (run / "transcript.log").read_text(errors="replace") if (run / "transcript.log").exists() else ""
    passed = (
        result.returncode == 0
        and "B1_REAL_GMII_LOOPBACK = PASS" in transcript
        and "Errors: 0" in transcript
        and "** Error" not in transcript
        and "** Fatal" not in transcript
    )
    provenance = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "result": "PASS" if passed else "FAIL",
        "model_sim_version": version,
        "command": command,
        "cwd": str(run),
        "exit_code": result.returncode,
        "scope": "B1 single-VL TX with unmodified stage5B0 MAC production RTL, real GMII electrical-loop model, independent Python Golden bytes/CRC, RX frame check, BAG at observed gmii_tx_en starts, malformed-message recovery and SN wrap",
        "source_inputs": [
            {
                "original": str(src),
                "original_sha256": sha(src),
                "snapshot": str(snap),
                "snapshot_sha256": sha(snap),
            }
            for src, snap in zip(SOURCES, snapshots)
        ],
        "golden_manifest_sha256": sha(golden / "manifest.json"),
    }
    (run / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    (run / "summary.json").write_text(json.dumps({
        "result": "PASS" if passed else "FAIL",
        "run": str(run),
        "model_sim_version": version,
        "exit_code": result.returncode,
    }, indent=2), encoding="utf-8")
    print(transcript[-5000:])
    print("B1_GMII_RUN", run, "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
