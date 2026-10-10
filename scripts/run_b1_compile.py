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
B0_SOURCES = [
    B0 / "deps" / "afdx_byte_fifo.v",
    B0 / "rtl" / "mac_crc32_byte.v",
    B0 / "rtl" / "mac_frame_store.v",
    B0 / "rtl" / "mac_gmii_tx.v",
    B0 / "rtl" / "mac_gmii_rx.v",
    B0 / "rtl" / "mac_gmii_core.v",
]
B1_SOURCES = sorted((ROOT / "rtl").glob("*.v"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    sources = B0_SOURCES + B1_SOURCES
    for path in sources:
        if not path.is_file():
            raise FileNotFoundError(path)

    run_index = 1
    while (ROOT / "runs" / f"compile_{run_index:03d}").exists():
        run_index += 1
    run = ROOT / "runs" / f"compile_{run_index:03d}"
    run.mkdir(parents=True)
    snapshots = run / "src"
    snapshots.mkdir()
    copied = []
    for path in sources:
        target = snapshots / path.name
        shutil.copy2(path, target)
        copied.append(target)

    shutil.copy2(MS.parent / "modelsim.ini", run / "modelsim.ini")
    os.chmod(run / "modelsim.ini", 0o666)
    lines = ["onerror {quit -code 2 -force}", "vlib work", "vmap work work"]
    for path in copied:
        lines.append(f"vlog -sv -work work {{{path.as_posix()}}}")
    lines.append("quit -code 0 -force")
    (run / "run.do").write_text("\n".join(lines) + "\n", encoding="utf-8")

    version = subprocess.check_output([str(MS / "vsim.exe"), "-version"], stderr=subprocess.STDOUT).decode(errors="replace").strip()
    env = os.environ.copy()
    env["MGLS_LICENSE_FILE"] = str(MS.parent / "LICENSE.TXT")
    command = [str(MS / "vsim.exe"), "-batch", "-modelsimini", "modelsim.ini", "-l", "transcript.log", "-do", "do run.do"]
    result = subprocess.run(command, cwd=run, env=env, capture_output=True, timeout=90)
    (run / "console.log").write_bytes(result.stdout + result.stderr)
    transcript_path = run / "transcript.log"
    transcript = transcript_path.read_text(errors="replace") if transcript_path.exists() else ""
    passed = result.returncode == 0 and "Errors: 0" in transcript and "** Error" not in transcript and "** Fatal" not in transcript
    provenance = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "result": "PASS" if passed else "FAIL",
        "model_sim_version": version,
        "command": command,
        "source_inputs": [{"original": str(p), "original_sha256": sha(p), "snapshot": str(c), "snapshot_sha256": sha(c)} for p, c in zip(sources, copied)],
        "scope": "Compile-only check of B1 production RTL with unmodified stage5B0 production MAC dependencies",
        "exit_code": result.returncode,
    }
    (run / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    (run / "summary.json").write_text(json.dumps({"result": "PASS" if passed else "FAIL", "run": str(run), "model_sim_version": version}, indent=2), encoding="utf-8")
    print(transcript[-2500:])
    print("B1_RTL_COMPILE", run, "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
