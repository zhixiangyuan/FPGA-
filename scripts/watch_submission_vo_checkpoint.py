"""Continue the fixed submission VO checkpoint, one verified session at a time.

This supervisor never changes the protected runner, its inputs, or the run's
saved evidence. Its own status and child logs live outside the official run.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

import msvcrt

from run_submission_vo_checkpoint import guard, sha, work_hashes


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "build/logs/submission_615a_vo_checkpoint_002"
STATE = ROOT / "build/logs/submission_615a_vo_watch_001"
RUNNER = ROOT / "scripts/run_submission_vo_checkpoint.py"


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_status(**fields: object) -> None:
    path = STATE / "status.json"
    status = json.loads(path.read_text()) if path.exists() else {}
    status.update(fields, updated_utc=utc())
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(status, indent=2) + "\n")
    temp.replace(path)


def check_paused() -> dict:
    summary = json.loads((RUN / "summary.json").read_text())
    if summary["result"] != "PAUSED" or summary.get("error") is not None:
        raise ValueError(f"Expected clean PAUSED summary, got {summary['result']}")
    if not summary["sessions"] or summary["sessions"][-1].get("exit_code") != 77:
        raise ValueError("Last session did not save a normal checkpoint")
    guard(RUN, summary)
    checkpoint = summary["checkpoint"]
    if not checkpoint or checkpoint["path"] not in checkpoint["files"]:
        raise ValueError("Missing recorded checkpoint")
    for name, digest in checkpoint["files"].items():
        if sha(RUN / name) != digest:
            raise ValueError(f"Checkpoint hash differs: {name}")
    if work_hashes(RUN) != checkpoint["work_hashes"]:
        raise ValueError("Compiled work library differs")
    if set(checkpoint["wire_artifacts"]) != {p.name for p in RUN.glob("*.csv")}:
        raise ValueError("Wire artifact set differs")
    for name, digest in checkpoint["wire_artifacts"].items():
        if sha(RUN / name) != digest:
            raise ValueError(f"Wire artifact hash differs: {name}")
    actual = {p.name for p in RUN.iterdir() if p.is_file() and p.name != "summary.json"}
    if actual != set(summary["artifacts"]):
        raise ValueError("Root artifact set differs")
    for name, digest in summary["artifacts"].items():
        if sha(RUN / name) != digest:
            raise ValueError(f"Root artifact hash differs: {name}")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if args.check_only:
        summary = check_paused()
        print(json.dumps({"result": "PAUSED_INTEGRITY_OK", "sessions": len(summary["sessions"]),
                          "checkpoint": summary["checkpoint"]["path"],
                          "controller_sha256": sha(RUNNER)}))
        return 0

    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / "supervisor.lock").open("a+b") as lock:
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError("VO checkpoint supervisor already running") from exc
        write_status(state="STARTING", supervisor_pid=os.getpid(), supervisor_started_utc=utc(),
                     supervisor_sha256=sha(Path(__file__)), runner_sha256=sha(RUNNER),
                     run=str(RUN), sessions=[])
        try:
            while True:
                summary = check_paused()
                index = len(summary["sessions"]) + 1
                command = [sys.executable, str(RUNNER), "--run", str(RUN),
                           "--session-minutes", "100"]
                child_log = STATE / f"runner_session_{index:03d}.log"
                with child_log.open("wb") as log:
                    proc = subprocess.Popen(command, cwd=ROOT, stdout=log,
                                            stderr=subprocess.STDOUT)
                    status = json.loads((STATE / "status.json").read_text())
                    sessions = status["sessions"]
                    record = {"index": index, "started_utc": utc(), "child_pid": proc.pid,
                              "command": command, "log": str(child_log)}
                    sessions.append(record)
                    write_status(state="RUNNING", child_pid=proc.pid, sessions=sessions)
                    code = proc.wait()
                record.update(child_exit_code=code, completed_utc=utc(),
                              log_sha256=sha(child_log))
                result = json.loads((RUN / "summary.json").read_text())
                record.update(runner_result=result["result"],
                              simulator_exit_code=result.get("exit_code"),
                              official_sessions=len(result["sessions"]))
                write_status(state="CHECKING", child_pid=None, sessions=sessions)
                if code != 0 or result["result"] == "FAIL":
                    raise RuntimeError(f"Runner session {index} failed: code={code}, result={result['result']}, error={result.get('error')}")
                if result["result"] == "PASS":
                    guard(RUN, result)
                    if result.get("exit_code") != 0 or result.get("error") is not None:
                        raise ValueError("Inconsistent final PASS status")
                    write_status(state="PASS", child_pid=None, sessions=sessions,
                                 official_summary_sha256=sha(RUN / "summary.json"))
                    return 0
                check_paused()
                write_status(state="PAUSED_VERIFIED", child_pid=None, sessions=sessions)
        except Exception as exc:
            write_status(state="STOPPED_ERROR", child_pid=None, error=repr(exc))
            raise
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


if __name__ == "__main__":
    raise SystemExit(main())
