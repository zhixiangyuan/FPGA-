from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
Eda = Path(r"D:\FPGA\eLinx3.0\bin\Passkey\bin\quartus_eda.exe")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a ModelSim functional .vo from the B1 independent eLinx synthesis project.")
    parser.add_argument("--project", type=Path, default=ROOT / "runs" / "elinx_001" / "AFDXNetwork", help="Independent B1 eLinx project directory after successful GUI Run Synthesis")
    parser.add_argument("--check-only", action="store_true", help="Read-only preflight; do not copy the project or run the EDA writer")
    args = parser.parse_args()
    project = args.project.resolve(strict=True)
    epr = project / "AFDXNetwork.epr"
    qpf = project / "AFDXNetwork.qpf"
    qsf = project / "AFDXNetwork.qsf"
    missing = [str(p) for p in (epr, qpf, qsf) if not p.is_file()]
    if missing:
        raise SystemExit("B1_EXPORT_PREFLIGHT = BLOCKED: GUI synthesis inputs are absent: " + ", ".join(missing))
    epr_text = epr.read_text(errors="replace")
    qsf_text = qsf.read_text(errors="replace")
    if "afdx_network_tx_top" not in epr_text or "EQ6HL45" not in epr_text or "CSG225" not in epr_text:
        raise SystemExit("B1 EPR top/device/package differs from the approved project")
    if not re.search(r"TOP_LEVEL_ENTITY\s+afdx_network_tx_top", qsf_text, re.IGNORECASE):
        raise SystemExit("Generated QSF does not select afdx_network_tx_top")

    synth = project / "AFDXNetwork.runs" / "synth_1"
    report = synth / "AFDXNetwork_utilization_synth.rpt"
    cluster = synth / "AFDXNetwork_cluster.xml"
    pack = synth / "AFDXNetwork_pack.tcl"
    if not all(p.is_file() for p in (report, cluster, pack)):
        raise SystemExit("B1_EXPORT_PREFLIGHT = BLOCKED: successful GUI synthesis report, cluster XML and Pack Tcl are required")
    report_text = report.read_text(errors="replace")
    if "Synthesis Status : Successful" not in report_text or "Top-level Entity Name : afdx_network_tx_top" not in report_text:
        raise SystemExit("B1_EXPORT_PREFLIGHT = BLOCKED: synthesis success/top is not confirmed")
    if 'device_name="EQ6HL45"' not in cluster.read_text(errors="replace") or 'set packageName "CSG225"' not in pack.read_text(errors="replace"):
        raise SystemExit("B1_EXPORT_PREFLIGHT = BLOCKED: actual cluster Device/Pack Package is not EQ6HL45/CSG225")
    manifest_path = project.parent / "project_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for row in manifest["source_manifest"]:
        snapshot = Path(row["snapshot"])
        original = Path(row["original"])
        if sha(snapshot) != row["snapshot_sha256"] or sha(original) != row["original_sha256"]:
            raise SystemExit("B1_EXPORT_PREFLIGHT = BLOCKED: source changed since approved project snapshot: " + str(snapshot))
    for match in re.finditer(r'VERILOG_FILE\s+(?:"([^"]+)"|(\S+))', qsf_text):
        source = Path(match.group(1) or match.group(2))
        if not source.is_absolute():
            source = project / source
        if not source.resolve().is_relative_to(project):
            raise SystemExit("B1_EXPORT_PREFLIGHT = BLOCKED: QSF references a source outside the independent B1 project: " + str(source))
    implemented_outputs = []
    for imple in (project / "AFDXNetwork.runs").glob("imple_*"):
        if imple.is_dir():
            implemented_outputs.extend(p for p in imple.rglob("*") if p.is_file() and (p.suffix.lower() in (".vo", ".vdo", ".sdo", ".sdf") or "utilization_imple" in p.name.lower()))
    if implemented_outputs:
        raise SystemExit("B1_EXPORT_PREFLIGHT = BLOCKED: unexpected Implementation outputs; inspect before continuing: " + ", ".join(map(str, implemented_outputs)))
    if args.check_only:
        print("B1_EXPORT_PREFLIGHT = PASS (read-only; no EDA/synthesis/Implementation executed)")
        return 0

    # Work on a fully separate copy: Quartus-compatible EDA writer never writes
    # into the GUI-generated project or its synthesis database.
    i = 1
    while (ROOT / "runs" / f"eda_export_{i:03d}").exists():
        i += 1
    run = ROOT / "runs" / f"eda_export_{i:03d}"
    work = run / "export_work" / "AFDXNetwork"
    work.parent.mkdir(parents=True)
    shutil.copytree(project, work)
    if not Eda.is_file():
        raise FileNotFoundError(Eda)
    command = [
        str(Eda),
        "--read_settings_files=on",
        "--write_settings_files=off",
        "--simulation=on",
        "--functional=on",
        "--tool=modelsim",
        "--format=verilog",
        "AFDXNetwork",
    ]
    result = subprocess.run(command, cwd=work, capture_output=True, timeout=300)
    (run / "export.log").write_bytes(result.stdout + result.stderr)
    netlist = work / "simulation" / "modelsim" / "AFDXNetwork.vo"
    text = netlist.read_text(errors="replace") if netlist.is_file() else ""
    module_names = sorted(set(re.findall(r"\bmodule\s+([A-Za-z_$][A-Za-z0-9_$]*)", text)))
    netlist_valid = netlist.is_file() and re.search(r"\bmodule\s+afdx_network_tx_top\b", text) is not None
    success = result.returncode == 0 and netlist_valid and "0 errors" in (result.stdout + result.stderr).decode(errors="replace").lower()
    provenance = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "result": "PASS" if success else "FAIL",
        "command": command,
        "working_directory": str(work),
        "gui_project": str(project),
        "gui_project_files": [{"path": str(p), "sha256": sha(p)} for p in (epr, qpf, qsf, report, cluster, pack, manifest_path)],
        "eda_writer": str(Eda),
        "eda_writer_sha256": sha(Eda),
        "exit_code": result.returncode,
        "generated_netlist": str(netlist) if netlist.is_file() else None,
        "generated_netlist_sha256": sha(netlist) if netlist.is_file() else None,
        "declared_modules": module_names,
        "netlist_top_verified": netlist_valid,
        "synthesis_or_fit_executed_by_this_script": False,
        "tool_output_notice": "Record the actual target printed by the EDA log. Previous B0 export identified EP1S80F1508C6 although its eLinx GUI project was EQ6HL45/CSG225; this .vo is a functional simulation model, not evidence of EQ6-native equivalence.",
    }
    (run / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    if success:
        delivered = run / "afdx_network_tx_top.vo"
        shutil.copy2(netlist, delivered)
        provenance["delivered_netlist"] = str(delivered)
        provenance["delivered_netlist_sha256"] = sha(delivered)
        (run / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
        print((result.stdout + result.stderr).decode(errors="replace")[-4000:])
        print("B1_FUNCTIONAL_NETLIST_EXPORT = PASS", delivered)
        print("MODEL_TOP=afdx_network_tx_top; MODEL_IS_NOT_EQ6_NATIVE_EQUIVALENCE")
        return 0
    print((result.stdout + result.stderr).decode(errors="replace")[-4000:])
    print("B1_FUNCTIONAL_NETLIST_EXPORT = FAIL/BLOCKED", run)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
