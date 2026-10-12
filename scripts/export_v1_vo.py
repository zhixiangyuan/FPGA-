"""Export a functional VO from the selected successful candidate synthesis project."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = Path(os.environ.get("AFDX_BUILD_ROOT", ROOT / "build"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, help="prepared eLinx project directory")
    args = parser.parse_args()
    if args.project_dir:
        project = args.project_dir.resolve()
    else:
        candidates = sorted((BUILD_ROOT / "elinx").glob("AFDXV1_*"))
        if not candidates:
            raise FileNotFoundError("Run scripts/prepare_v1_elinx.py first")
        project = candidates[-1]

    audit_path = project / "synthesis_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("result") != "PASS":
        raise RuntimeError("VO export requires a passing synthesis audit for this project")
    synthesis_dir = project / "AFDXV1.runs" / "synth_1"
    for name, digest in audit["synthesis_artifact_hashes"].items():
        if sha(synthesis_dir / name) != digest:
            raise RuntimeError(f"Synthesis artifact changed after audit: {name}")
    project_manifest = json.loads((project / "project_manifest.json").read_text(encoding="utf-8"))
    for row in project_manifest["sources"]:
        canonical = ROOT / row["canonical_source"]
        snapshot = project / row["snapshot"]
        if sha(canonical) != row["sha256"] or sha(snapshot) != row["snapshot_sha256"]:
            raise RuntimeError(f"Project source hash mismatch: {row['canonical_source']}")

    run_root = BUILD_ROOT / "logs"
    run_root.mkdir(parents=True, exist_ok=True)
    index = 1
    while (run_root / f"eda_export_{index:03d}").exists():
        index += 1
    run = run_root / f"eda_export_{index:03d}"
    work = run / "export_work" / "AFDXV1"
    work.parent.mkdir(parents=True)
    shutil.copytree(project, work)
    qsf = work / "AFDXV1.qsf"
    if qsf.exists():
        text = qsf.read_text(encoding="utf-8", errors="replace")
        text = text.replace(project.as_posix(), work.as_posix())
        text = text.replace(str(project), str(work))
        qsf.write_text(text, encoding="utf-8")

    elinx_home = Path(os.environ.get("ELINX_HOME", r"D:\FPGA\eLinx3.0"))
    tool = elinx_home / "bin" / "Passkey" / "bin" / "quartus_eda.exe"
    if not tool.is_file():
        raise FileNotFoundError(f"eLinx functional netlist exporter not found: {tool}")
    command = [str(tool), "--read_settings_files=on", "--write_settings_files=off",
               "--simulation=on", "--functional=on", "--tool=modelsim",
               "--format=verilog", "AFDXV1"]
    started = datetime.now(timezone.utc).isoformat()
    result = subprocess.run(command, cwd=work, capture_output=True, timeout=300)
    log = result.stdout + result.stderr
    (run / "export.log").write_bytes(log)
    generated = work / "simulation" / "modelsim" / "AFDXV1.vo"
    if result.returncode != 0 or not generated.is_file():
        raise RuntimeError(f"Functional VO export failed; see {run / 'export.log'}")
    if not re.search(r"\bmodule\s+AFDX_top\b", generated.read_text(errors="replace")):
        raise RuntimeError("Exported VO does not contain top module AFDX_top")
    delivered = run / "AFDX_top.vo"
    shutil.copy2(generated, delivered)
    provenance = {
        "result": "PASS",
        "started_utc": started,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "exit_code": result.returncode,
        "source_project": str(project),
        "export_project_copy": str(work),
        "eda_tool_sha256": sha(tool),
        "export_log_sha256": sha(run / "export.log"),
        "delivered_netlist": str(delivered),
        "delivered_netlist_sha256": sha(delivered),
        "synthesis_audit_sha256": sha(audit_path),
        "device_GUI": "EQ6HL45/CSG225",
        "model_backend": "EP1S80F1508C6 / Stratix compatibility primitive model",
        "EQ6_NATIVE_NETLIST_EQUIVALENCE": "NOT VERIFIED",
        "synthesis_or_fit_executed": False,
    }
    (run / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(provenance, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
