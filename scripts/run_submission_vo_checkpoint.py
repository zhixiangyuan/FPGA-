"""Run the fixed real-VO candidate in resumable, wall-time-bounded sessions.

Uses the original optimized VO image and unchanged Golden/RTL reference. A
PAUSED checkpoint is not acceptance. Only the original complete verifier can
produce PASS after the testbench finishes. Restore keeps the same run directory.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess

from run_submission_615a import ROOT, MS, sha, verify, compare_rtl_vo


def save(path: Path, data: dict) -> None:
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(data, indent=2) + "\n")
    temp.replace(path)


def work_hashes(run: Path) -> dict:
    return {p.relative_to(run).as_posix(): sha(p) for p in sorted((run / "work").rglob("*"))
            if p.is_file() and "lock" not in p.name.lower()}


def guard(run: Path, summary: dict) -> None:
    if summary["RTL_DUT_compiled"] or summary["force_used"] or summary["shortened_timers"]:
        raise ValueError("Expected unshortened real VO")
    if summary["clock_ns"] != 8 or summary["BAG_cycles"] != 125000:
        raise ValueError("Unexpected clock/BAG")
    if sha(run / "modelsim.ini") != summary["modelsim_ini_sha256"]:
        raise ValueError("Simulation library configuration changed")
    for name, digest in summary["inputs"].items():
        p = Path(name)
        if sha(p) != digest or sha(run / p.name) != digest:
            raise ValueError(f"Original input changed: {p}")
    for name, digest in summary["golden"].items():
        if sha(run / "golden" / name) != digest:
            raise ValueError(f"Golden changed: {name}")
    reference = Path(summary["reference_RTL_run"])
    for name, digest in summary["rtl_reference_hashes"].items():
        if sha(reference / name) != digest:
            raise ValueError(f"RTL reference changed: {name}")
    baseline = json.loads((reference / "summary.json").read_text())
    if baseline["result"] != "PASS" or baseline["golden"] != summary["golden"]:
        raise ValueError("Expected same-Golden completed RTL reference")
    if sha(Path(__file__)) != summary["checkpoint_controller_sha256"] or sha(run / Path(__file__).name) != summary["checkpoint_controller_sha256"]:
        raise ValueError("Checkpoint controller changed")


def prepare(source: Path, reference: Path) -> Path:
    old = json.loads((source / "summary.json").read_text())
    commands = (source / "run.do").read_text()
    vlog = [line.split()[-1] for line in commands.splitlines() if line.startswith("vlog ")]
    if set(vlog) != {"altera_primitives.v", "220model.v", "stratix_atoms.v", "AFDX_top.vo", "tb_submission_615a.sv"} or len(vlog) != 5:
        raise ValueError("Source optimized image must originate from the real-VO-only compile flow")
    parent = ROOT / "build/logs"
    index = 1
    while (parent / f"submission_615a_vo_checkpoint_{index:03d}").exists():
        index += 1
    run = parent / f"submission_615a_vo_checkpoint_{index:03d}"
    run.mkdir()
    for name, digest in old["inputs"].items():
        p = source / Path(name).name
        if sha(p) != digest:
            raise ValueError(f"Source snapshot changed: {p}")
        shutil.copy2(p, run / p.name)
    for name in ("work", "golden"):
        shutil.copytree(source / name, run / name)
    for name in ("modelsim.ini",):
        shutil.copy2(source / name, run / name)
    shutil.copy2(source / "summary.json", run / "source_run_summary.json")
    shutil.copy2(source / "run.do", run / "source_run.do")
    shutil.copy2(Path(__file__), run / Path(__file__).name)
    summary = {k: v for k, v in old.items() if k not in ("evidence", "artifacts", "exit_code", "error", "completed_utc", "modelsim_pid")}
    summary.update(result="PREPARED", started_utc=None, created_utc=datetime.now(timezone.utc).isoformat(),
                   reference_RTL_run=str(reference), source_run=str(source),
                   source_run_summary_sha256=sha(run / "source_run_summary.json"),
                   original_compile_do_sha256=sha(run / "source_run.do"),
                   modelsim_ini_sha256=sha(run / "modelsim.ini"),
                   checkpoint_controller_sha256=sha(Path(__file__)), sessions=[],
                   initial_work_hashes=work_hashes(run), checkpoint=None)
    guard(run, summary)
    if work_hashes(source) != summary["initial_work_hashes"]:
        raise ValueError("Copied optimized work library differs from original")
    save(run / "summary.json", summary)
    return run


def execute(run: Path, minutes: float, chunk_us: int, pause_at: str | None) -> int:
    summary_path = run / "summary.json"
    summary = json.loads(summary_path.read_text())
    if summary["result"] not in ("PREPARED", "PAUSED"):
        raise ValueError("Only PREPARED or PAUSED runs can start a session")
    guard(run, summary)
    restore = summary["checkpoint"]
    if restore:
        for name, digest in restore["files"].items():
            if sha(run / name) != digest:
                raise ValueError(f"Checkpoint changed: {name}")
        if work_hashes(run) != restore["work_hashes"]:
            raise ValueError("Checkpoint compiled library changed")
        for name, digest in restore["wire_artifacts"].items():
            if sha(run / name) != digest:
                raise ValueError(f"Paused output changed: {name}")
    index = len(summary["sessions"]) + 1
    prefix = f"session_{index:03d}"
    checkpoint_dir = run / "checkpoints" / prefix
    deadline_ms = int(datetime.now(timezone.utc).timestamp() * 1000 + minutes * 60000)
    if pause_at:
        dt = datetime.fromisoformat(pause_at)
        if dt.tzinfo is None:
            raise ValueError("pause-at requires an explicit timezone")
        deadline_ms = min(deadline_ms, int(dt.timestamp() * 1000))
    lines = ["onerror {quit -code 2 -force}"]
    if not restore:
        lines += ["vsim -t 1ps work.sub615a_opt"]
    lines += ["onfinish exit", f"set session_deadline {deadline_ms}", "while {1} {",
              f"  run {chunk_us} us", "  if {[runStatus] ne \"ready\"} {error \"Unexpected simulation break\"}",
              "  if {[clock milliseconds] >= $session_deadline} {",
              f"    checkpoint -dir {{{checkpoint_dir.as_posix()}}}",
              '    puts "SESSION_CHECKPOINT_SAVED time=$now"',
              "    quit -code 77 -force", "  }", "}"]
    dofile = run / f"{prefix}.do"
    dofile.write_text("\n".join(lines) + "\n")
    transcript = run / f"{prefix}_transcript.log"
    console = run / f"{prefix}_console.log"
    command = [str(MS / "vsim.exe"), "-batch", "-modelsimini", "modelsim.ini", "-l", transcript.name, "-do", f"do {dofile.name}"]
    if restore:
        command += ["-restore", str(run / restore["path"])]
    session = dict(index=index, started_utc=datetime.now(timezone.utc).isoformat(),
                   pause_deadline_utc=datetime.fromtimestamp(deadline_ms / 1000, timezone.utc).isoformat(),
                   restored_from=None if restore is None else restore["path"],
                   command=command, do_sha256=sha(dofile), transcript=transcript.name, console=console.name)
    summary["sessions"].append(session)
    summary.update(result="RUNNING", active_session=index)
    if summary["started_utc"] is None:
        summary["started_utc"] = session["started_utc"]
    save(summary_path, summary)
    env = os.environ.copy()
    env.setdefault("MGLS_LICENSE_FILE", str(MS.parent / "LICENSE.TXT"))
    with console.open("wb") as log:
        proc = subprocess.Popen(command, cwd=run, env=env, stdout=log, stderr=subprocess.STDOUT)
        summary["modelsim_pid"] = proc.pid
        session["modelsim_pid"] = proc.pid
        save(summary_path, summary)
        print(f"CHECKPOINT_VO_RUN {run} SESSION {index} PID {proc.pid}", flush=True)
        wall_cap = max(0, deadline_ms / 1000 - datetime.now(timezone.utc).timestamp()) + 300
        try:
            code = proc.wait(timeout=wall_cap)
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdout=log, stderr=subprocess.STDOUT)
            proc.wait(timeout=30)
            code = -1
    text = transcript.read_text(errors="replace")
    console_text = console.read_text(errors="replace")
    session.update(exit_code=code, completed_utc=datetime.now(timezone.utc).isoformat(),
                   transcript_sha256=sha(transcript), console_sha256=sha(console))
    (run / "transcript.log").write_bytes(b"\n".join((run / s["transcript"]).read_bytes() for s in summary["sessions"]))
    error = None
    evidence = {}
    try:
        guard(run, summary)
        if sha(dofile) != session["do_sha256"]:
            raise ValueError("Session commands changed")
        if any(marker in text or marker in console_text for marker in ("** Error", "** Fatal")):
            raise ValueError("Simulator error/fatal; inspect session transcript")
        cpt = checkpoint_dir / "vsim.cpt"
        if code == 77 and "SESSION_CHECKPOINT_SAVED" in console_text and cpt.exists() and cpt.stat().st_size > 0:
            summary.update(result="PAUSED", checkpoint=dict(path=cpt.relative_to(run).as_posix(),
                files={p.relative_to(run).as_posix(): sha(p) for p in checkpoint_dir.rglob("*") if p.is_file()},
                work_hashes=work_hashes(run),
                wire_artifacts={p.name: sha(p) for p in run.glob("*.csv")},
                saved_utc=session["completed_utc"]))
        elif code == 0 and "SUBMISSION_615A_PASS" in text:
            golden = json.loads((run / "golden/cases.json").read_text())
            evidence = verify(run, golden)
            evidence.update(compare_rtl_vo(run, Path(summary["reference_RTL_run"])))
            guard(run, summary)
            summary.update(result="PASS", completed_utc=session["completed_utc"])
        else:
            raise ValueError(f"Unexpected simulator exit {code}; neither verified checkpoint nor complete TB PASS")
    except (AssertionError, ValueError, KeyError, IndexError, OSError) as exc:
        error = str(exc)
        summary.update(result="FAIL", completed_utc=session["completed_utc"])
    summary.update(exit_code=code, error=error, evidence=evidence,
                   artifacts={p.name: sha(p) for p in run.iterdir() if p.is_file() and p.name != "summary.json"})
    save(summary_path, summary)
    print(json.dumps(dict(run=str(run), result=summary["result"], error=error,
                          checkpoint=None if summary["checkpoint"] is None else summary["checkpoint"]["path"], evidence=evidence)), flush=True)
    return 1 if summary["result"] == "FAIL" else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-from", type=Path)
    mode.add_argument("--run", type=Path)
    parser.add_argument("--rtl-reference", type=Path)
    parser.add_argument("--session-minutes", type=float, default=100)
    parser.add_argument("--chunk-us", type=int, default=100)
    parser.add_argument("--pause-at")
    args = parser.parse_args()
    if args.session_minutes < 0 or not 1 <= args.chunk_us <= 1000:
        raise ValueError("Invalid session duration or simulation chunk")
    if args.prepare_from:
        if not args.rtl_reference:
            raise ValueError("prepare-from requires rtl-reference")
        run = prepare(args.prepare_from.resolve(), args.rtl_reference.resolve())
        print(json.dumps(dict(result="PREPARED", run=str(run))))
        return 0
    return execute(args.run.resolve(), args.session_minutes, args.chunk_us, args.pause_at)


if __name__ == "__main__":
    raise SystemExit(main())
