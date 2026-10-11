"""Freeze the B2 candidate implementation and executed evidence by SHA-256."""

from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"


def entry(path: Path) -> dict:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": h.hexdigest()}


def main() -> None:
    sources = sorted((ROOT / "rtl").glob("*.v"))
    sources += sorted((ROOT / "sim").glob("*.sv"))
    sources += sorted((ROOT / "scripts").glob("*.py"))
    sources += sorted((ROOT / "scripts").glob("*.ps1"))
    reports = [ROOT / "阶段5-B2_SN状态转换待审核.md",
               ROOT / "阶段5-B2_SN规则冻结与状态转换表.md",
               ROOT / "阶段5-B2_AFDX接收协议开发与闭环验收报告.md",
               ROOT / "阶段5-B2-4_综合与功能网表验收实施计划.md",
               RUNS / "current_status.json"]
    evidence = []
    full=sorted(RUNS.glob("full_[0-9][0-9][0-9]"))[-1].name
    history=sorted(RUNS.glob("history_[0-9][0-9][0-9]"))[-1].name
    for name in ("unit_002", "pressure_001", "loop_004", "history_001",full,history):
        run = RUNS / name
        for filename in ("summary.json", "transcript.log", "console.log", "waves.wlf",
                         "actual_payload.csv", "actual_tx_gmii.csv", "sn_decisions.csv", "verification.json"):
            path = run / filename
            if path.exists():
                evidence.append(path)
        golden = run / "golden"
        if golden.exists():
            evidence += sorted(p for p in golden.iterdir() if p.is_file())
    for path in sources + reports + evidence:
        if not path.is_file():
            raise FileNotFoundError(path)
    data = {
        "local_date": "2026-10-11",
        "scope": "Captain-approved B2-1/B2-2 single-VL functional baseline, frozen before B2-4; full integration/synthesis remain incomplete",
        "b1_frozen_git_commit": "302b944afc111aa232688d700911704d667c7a37",
        "sources": [entry(p) for p in sources],
        "reports_and_status": [entry(p) for p in reports],
        "executed_evidence": [entry(p) for p in evidence],
    }
    output = ROOT / "B2_EVIDENCE_MANIFEST.json"
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"B2_EVIDENCE_MANIFEST = {output}")
    print(f"SOURCES={len(sources)} REPORTS={len(reports)} EVIDENCE={len(evidence)}")


if __name__ == "__main__":
    main()
