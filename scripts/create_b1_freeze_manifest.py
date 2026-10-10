"""Record the approved B1 sources and original evidence without rerunning tests."""

from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT.parent
WORKSPACE = INTEGRATION.parent


def digest(path: Path) -> dict:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": h.hexdigest()}


def main() -> None:
    local_sources = sorted((ROOT / "rtl").glob("*.v"))
    local_sources += sorted((ROOT / "sim").glob("*.sv"))
    local_sources += sorted((ROOT / "scripts").glob("*.py"))
    local_sources += sorted(ROOT.glob("*.ps1"))
    frozen_dependencies = sorted((INTEGRATION / "stage5B0_selfmac_20261010" / "rtl").glob("*.v"))
    frozen_dependencies += sorted((INTEGRATION / "stage3B2_20261008" / "rtl").glob("*.v"))
    report_files = [
        ROOT / "阶段5-B1_单VL_AFDX发送协议完整开发与验收报告.md",
        ROOT / "阶段5-B1-N_队长功能网表复验指南.md",
        ROOT / "阶段5-B1-N_综合Warning与封装I_O审计.md",
        ROOT / "runs" / "current_status.json",
    ]
    run = ROOT / "runs" / "netlist_004"
    evidence = [
        ROOT / "runs" / "acceptance_003" / "summary.json",
        INTEGRATION / "stage5B0_selfmac_20261010" / "runs" / "acceptance_005" / "summary.json",
        INTEGRATION / "stage3B2_20261008" / "runs" / "run_014" / "summary.json",
        ROOT / "runs" / "eda_export_001" / "afdx_network_tx_top.vo",
        ROOT / "runs" / "eda_export_001" / "provenance.json",
        ROOT / "evidence" / "gui_success_001" / "artifact_hashes.json",
        *[run / name for name in (
            "summary.json", "provenance.json", "transcript.log", "console.log",
            "waves.wlf", "actual_tx_gmii.csv", "actual_rx_client.csv",
            "frame_progress.csv", "afdx_network_tx_top.vo", "tb_b1_netlist_full.sv",
            "altera_primitives.v", "220model.v", "stratix_atoms.v",
        )],
        *sorted((run / "golden").glob("*")),
    ]
    for path in local_sources + frozen_dependencies + report_files + evidence:
        if not path.is_file():
            raise FileNotFoundError(path)
    status = json.loads((ROOT / "runs" / "current_status.json").read_text(encoding="utf-8"))
    states = status["states"]
    expected = {
        "STAGE5B1_RESULT": "PASS",
        "B1_POST_SYNTH_FUNCTIONAL_SIM": "PASS",
        "POST_SYNTH_TIMING": "NOT VERIFIED",
        "EQ6_NATIVE_NETLIST_EQUIVALENCE": "NOT VERIFIED",
        "CSG225_DIAGNOSTIC_TOP_IO_FIT": "INCOMPATIBLE",
    }
    for key, value in expected.items():
        if states.get(key) != value:
            raise ValueError(f"Unexpected {key}: {states.get(key)}")
    data = {
        "freeze_local_date": "2026-10-11",
        "approval": "Captain approved Stage 5-B1 for verified single-VL transmit functionality only",
        "states": {key: states[key] for key in expected},
        "source": [digest(p) for p in local_sources],
        "frozen_dependencies": [digest(p) for p in frozen_dependencies],
        "report_and_status": [digest(p) for p in report_files],
        "original_evidence": [digest(p) for p in evidence],
        "note": "Evidence remains at its original path; the Git snapshot stores these hashes and does not rerun or alter the evidence.",
    }
    output = ROOT / "B1_FREEZE_MANIFEST.json"
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"B1_FREEZE_MANIFEST = {output}")
    print(f"SOURCES = {len(local_sources)} DEPENDENCIES = {len(frozen_dependencies)} EVIDENCE = {len(evidence)}")


if __name__ == "__main__":
    main()
