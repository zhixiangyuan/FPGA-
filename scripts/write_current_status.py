from pathlib import Path
import hashlib
import json
import subprocess
import sys
import re
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
B0 = Path(r"D:\FPGA\captain_integration\stage5B0_selfmac_20261010")
STAGE3 = Path(r"D:\FPGA\captain_integration\stage3B2_20261008")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def latest(prefix: str, base=ROOT / "runs") -> Path:
    paths = sorted(p for p in base.glob(prefix + "_*") if p.is_dir())
    if not paths:
        raise FileNotFoundError(prefix)
    return paths[-1]


def read_summary(path: Path) -> dict:
    return json.loads((path / "summary.json").read_text(encoding="utf-8-sig"))


def main() -> int:
    gmii = latest("gmii")
    stall = latest("stall")
    clk125 = latest("clk125")
    abort = latest("abort")
    b0_acceptance = latest("acceptance", B0 / "runs")
    stage3_run = latest("run", STAGE3 / "runs")
    b0_states = read_summary(b0_acceptance)["states"]
    epr = ROOT / "runs" / "elinx_001" / "AFDXNetwork" / "AFDXNetwork.epr"
    source_paths = sorted((ROOT / "rtl").glob("*.v")) + sorted((ROOT / "sim").glob("*.sv"))
    synth_report = epr.parent / "AFDXNetwork.runs" / "synth_1" / "AFDXNetwork_utilization_synth.rpt"
    synthesis = "NOT RUN"
    synth_check_output = "GUI synthesis report not present"
    if synth_report.exists():
        check = subprocess.run([sys.executable, str(ROOT / "scripts" / "export_b1_functional_netlist.py"), "--project", str(epr.parent), "--check-only"], capture_output=True, text=True)
        synthesis = "PASS" if check.returncode == 0 else "BLOCKED"
        synth_check_output = check.stdout + check.stderr
    netlist_runs = sorted(p for p in (ROOT / "runs").glob("netlist_*") if p.is_dir() and re.fullmatch(r'netlist_\d+',p.name))
    full_runs = [p for p in netlist_runs if (p/'tb_b1_netlist_full.sv').exists()]
    basic_runs = [p for p in netlist_runs if (p/'tb_b1_netlist_loopback.sv').exists()]
    netlist_result = "NOT RUN"
    basic_result = "NOT RUN"
    if full_runs:
        netlist_result = read_summary(full_runs[-1])["result"] if (full_runs[-1] / "summary.json").exists() else "RUNNING"
    if basic_runs:
        basic_result = read_summary(basic_runs[-1])["result"] if (basic_runs[-1] / "summary.json").exists() else "RUNNING"
    data = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "states": {
            "B1_PROTOCOL_RTL": "PASS" if all(read_summary(p)["result"] == "PASS" for p in (gmii,stall,clk125)) else "FAIL",
            "B1_REAL_MAC_GMII": read_summary(gmii)["result"],
            "B1_READY_STALL": read_summary(stall)["result"],
            "B1_125M_BAG_RTL": read_summary(clk125)["result"],
            "B0_ABORT_RECOVERY": read_summary(abort)["result"],
            "STAGE1_REGRESSION": b0_states["STAGE1_REGRESSION"],
            "STAGE2_REGRESSION": b0_states["STAGE2_REGRESSION"],
            "STAGE3B2_REGRESSION": read_summary(stage3_run)["summary"]["STAGE3B2_RESULT"],
            "STAGE5B0_REGRESSION": b0_states["SELF_MAC_STAGE5B0_RESULT"],
            "B1_ELINX_SYNTHESIS": synthesis,
            "B1_POST_SYNTH_FUNCTIONAL_SIM": netlist_result,
            "B1_POST_SYNTH_BASIC_SIM": basic_result,
            "CSG225_DIAGNOSTIC_TOP_IO_FIT": "INCOMPATIBLE" if synth_report.exists() and "Total Pins : 579" in synth_report.read_text(errors="replace") else "NOT VERIFIED",
            "POST_SYNTH_TIMING": "NOT VERIFIED",
            "EQ6_NATIVE_NETLIST_EQUIVALENCE": "NOT VERIFIED",
            "IMPLEMENTATION": "NOT RUN",
            "BITSTREAM": "NOT RUN",
        },
        "evidence": {
            "b1_gmii": str(gmii),
            "b1_ready_stall": str(stall),
            "b1_125m_rtl": str(clk125),
            "b0_abort_contract": str(abort),
            "stage1_stage2_stage3b2": str(stage3_run),
            "stage5b0_acceptance": str(b0_acceptance),
            "elinx_project": str(epr),
            "elinx_project_manifest": str(epr.parents[1] / "project_manifest.json"),
            "invalid_wrapper_run_preserved": str(ROOT / "runs" / "acceptance_001"),
        },
        "source_sha256": [{"path": str(p), "sha256": sha(p)} for p in source_paths],
        "limits": [
            "Functional RTL/GMII evidence does not establish physical timing or 100 Mbps performance.",
            "See B1 synthesis and netlist states; unexecuted or blocked items are not PASS.",
            "No complete AFDX compliance claim is made.",
        ],
    }
    data["synthesis_preflight"] = synth_check_output
    if full_runs:
        data["evidence"]["b1_netlist_full"] = str(full_runs[-1])
    if basic_runs:
        data["evidence"]["b1_netlist_basic"] = str(basic_runs[-1])
    required = [v for k,v in data["states"].items() if k not in ("POST_SYNTH_TIMING","EQ6_NATIVE_NETLIST_EQUIVALENCE","IMPLEMENTATION","BITSTREAM","CSG225_DIAGNOSTIC_TOP_IO_FIT")]
    # Captain approved the B1 functional milestone on 2026-10-11. This PASS
    # covers only the required functional states; the excluded physical and
    # device-model states remain separate and unverified.
    data["states"]["STAGE5B1_RESULT"] = "FAIL" if "FAIL" in required else "PASS" if all(v == "PASS" for v in required) else "IN_PROGRESS" if "RUNNING" in required else "BLOCKED_PENDING_ELINX_AND_NETLIST"
    data["captain_review"] = {"decision": "APPROVED", "date_local": "2026-10-11", "scope": "Verified Stage 5-B1 single-VL transmit functionality only"}
    data["scope"] = "Approved B1 single-VL functional milestone; IO/package adaptation, native EQ6 equivalence and Setup/Hold are independent pending items, not claims included in STAGE5B1_RESULT"
    out = ROOT / "runs" / "current_status.json"
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print("CURRENT_STATUS", out)
    for key, value in data["states"].items():
        print(f"{key} = {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
