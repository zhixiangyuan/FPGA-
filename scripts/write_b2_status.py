"""Summarize only executed B2 evidence; SN approval remains a hard gate."""

from pathlib import Path
from datetime import datetime, timezone
import json

ROOT = Path(__file__).resolve().parents[1]


def latest(prefix: str) -> Path:
    runs = sorted((ROOT / "runs").glob(prefix + "_[0-9][0-9][0-9]"))
    if not runs:
        raise FileNotFoundError(prefix)
    return runs[-1]


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> None:
    unit, pressure, loop, history = [latest(p) for p in ("unit", "pressure", "loop", "history")]
    full=latest("full")
    full_s=read(full/"summary.json")
    full_audit=read(full/"verification.json")
    full_ok=full_s["result"]==full_audit["result"]=="PASS"
    unit_s = read(unit / "summary.json")
    pressure_s = read(pressure / "summary.json")
    loop_s = read(loop / "summary.json")
    loop_audit = read(loop / "verification.json")
    history_s = read(history / "summary.json")
    b1_s = read(Path(history_s["b1_acceptance"]) / "summary.json")
    b0_s = read(Path(history_s["b0_acceptance"]) / "summary.json")
    s3_s = read(Path(history_s["stage3b2_regression"]) / "summary.json")
    history_ok = (history_s["exit_code"] == 0 and history_s["protected_files_restored"]
                  and b1_s["states"]["STAGE5B1_RESULT"] == "PASS"
                  and b0_s["states"]["SELF_MAC_STAGE5B0_RESULT"] == "PASS"
                  and all(s3_s["summary"][k] == "PASS" for k in
                          ("STAGE1_REGRESSION", "STAGE2_REGRESSION", "STAGE3B2_RESULT")))
    states = {
        "B2_RX_PROTOCOL_RTL": "PASS" if full_ok and unit_s["result"]=="PASS" else "FAIL",
        "B2_EXCEPTION_RECOVERY": "PASS" if full_ok else "FAIL",
        "B2_RX_PARSER_RTL": unit_s["result"],
        "B2_DUAL_BUFFER_ATOMIC": pressure_s["result"],
        "B2_REAL_MAC_CANDIDATE_LOOP": "PASS" if loop_s["result"] == loop_audit["result"] == "PASS" else "FAIL",
        "B2_PROTOCOL_ERROR_FILTER": "PASS" if loop_audit["protocol_mutation_frames_with_correct_fcs"] == 9 else "FAIL",
        "B2_FIFO_PRESSURE_RESET": "PASS" if loop_s["result"] == "PASS" else "FAIL",
        "STAGE1_REGRESSION": "PASS" if history_ok else "FAIL",
        "STAGE2_REGRESSION": "PASS" if history_ok else "FAIL",
        "STAGE3B2_REGRESSION": "PASS" if history_ok else "FAIL",
        "STAGE5B0_REGRESSION": "PASS" if history_ok else "FAIL",
        "STAGE5B1_REGRESSION": "PASS" if history_ok else "FAIL",
        "B2_SN_PRODUCTION_RULE": "APPROVED_2026_10_11",
        "B2_SN_WRAP_DUPLICATE_REORDER_TEST": "PASS" if full_ok else "FAIL",
        "B2_FULL_PROTOCOL_END_TO_END": "PASS" if full_ok else "FAIL",
        "B2_SN_CAPACITY_RESET": "PASS" if full_ok else "FAIL",
        "B2_1_FUNCTIONAL_RESULT": "PASS" if unit_s["result"]=="PASS" and pressure_s["result"]=="PASS" else "FAIL",
        "B2_2_PROTOCOL_LOOP_RESULT": "PASS" if full_ok else "FAIL",
        "B2_4_SYNTHESIS": "NOT RUN",
        "B2_FORMAL_TOP_INTEGRATION": "NOT RUN",
        "B2_4_SYNTHESIS": "NOT RUN",
        "B2_POST_SYNTH_FUNCTIONAL": "NOT RUN",
        "POST_SYNTH_TIMING": "NOT VERIFIED",
        "EQ6_NATIVE_NETLIST_EQUIVALENCE": "NOT VERIFIED",
        "DIAGNOSTIC_IO_FIT": "INCOMPATIBLE",
        "IMPLEMENTATION": "NOT RUN",
        "BITSTREAM": "NOT RUN",
        "STAGE5B2_RESULT": "IN_PROGRESS_B2_3_B2_4" if full_ok and history_ok else "FAIL",
    }
    data = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Executed B2-1/B2-2 single-VL parser, approved SN gate and real B1/B0 GMII application delivery; awaiting final captain review",
        "states": states,
        "evidence": {"unit": str(unit), "pressure": str(pressure), "loop": str(loop),
                     "history": str(history),"full_sn_loop":str(full),
                     "sn_decision_table": str(ROOT / "阶段5-B2_SN规则冻结与状态转换表.md")},
        "limits": [
            "Final application output is behind the approved SN gate; only the single-VL engineering profile is verified.",
            "Official AFDX_top byte profile and frame boundary remain unanswered; no B2-3 integration was performed.",
            "No synthesis, Implementation, Bitstream or hardware download was performed for B2.",
        ],
    }
    output = ROOT / "runs" / "current_status.json"
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("B2_STATUS", output)
    for key, value in states.items():
        print(f"{key} = {value}")


if __name__ == "__main__":
    main()
