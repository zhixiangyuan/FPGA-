"""Bounded two-process VO throughput experiment; never full acceptance.

Uses different time intervals of the same unchanged VO/TB/Golden. A private
checkpoint seed supplies each interval's real preceding state. Serial and
parallel copies must produce identical complete CSVs and RTL wire prefixes.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from run_submission_615a import ROOT, MS, sha
from check_live_submission_vo import complete_rows, compare_prefix

CSV_NAMES = ("wire_tx.csv", "wire_rx.csv", "packets.csv", "peer_packets.csv", "metadata.csv")
K = ctypes.WinDLL("kernel32", use_last_error=True)


class Memory(ctypes.Structure):
    _fields_ = [("length", wintypes.DWORD), ("load", wintypes.DWORD)] + [(n, ctypes.c_ulonglong) for n in
        ("total_physical", "available_physical", "total_pagefile", "available_pagefile", "total_virtual", "available_virtual", "extended")]


class Entry(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("usage", wintypes.DWORD), ("pid", wintypes.DWORD),
                ("heap", ctypes.c_size_t), ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
                ("parent", wintypes.DWORD), ("priority", wintypes.LONG), ("flags", wintypes.DWORD),
                ("image", wintypes.WCHAR * 260)]


class Counters(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("faults", wintypes.DWORD)] + [(n, ctypes.c_size_t) for n in
        ("peak_working", "working", "peak_paged", "paged", "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile", "private")]


K.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
K.OpenProcess.restype = wintypes.HANDLE
K.CloseHandle.argtypes = [wintypes.HANDLE]
K.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
K.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
K.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
K.Process32NextW.argtypes = K.Process32FirstW.argtypes
K.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
K.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(Memory)]
P = ctypes.WinDLL("psapi", use_last_error=True)
P.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]


def available_mib() -> float:
    m = Memory(); m.length = ctypes.sizeof(m)
    if not K.GlobalMemoryStatusEx(ctypes.byref(m)):
        raise ctypes.WinError(ctypes.get_last_error())
    return m.available_physical / 1048576


def children() -> dict:
    snap = K.CreateToolhelp32Snapshot(2, 0)
    if snap == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    entry = Entry(); entry.size = ctypes.sizeof(entry); result = {}
    try:
        ok = K.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            result[entry.pid] = dict(parent=entry.parent, image=entry.image)
            ok = K.Process32NextW(snap, ctypes.byref(entry))
    finally:
        K.CloseHandle(snap)
    return result


def clone(source: Path, checkpoint: Path, target: Path) -> None:
    target.mkdir()
    for name in ("work", "golden"):
        shutil.copytree(source / name, target / name)
    for name in ("modelsim.ini",) + CSV_NAMES:
        shutil.copy2(source / name, target / name)
    shutil.copy2(checkpoint, target / "start.cpt")


def group(jobs: list[dict], stop_at: datetime, duration_us: int, save_seed: bool = False) -> dict:
    if len(jobs) > 1 and available_mib() < 1536:
        raise RuntimeError("Less than 1536 MiB available before two-worker experiment")
    env = os.environ.copy(); env.setdefault("MGLS_LICENSE_FILE", str(MS.parent / "LICENSE.TXT"))
    start = time.monotonic(); launched = []; handles = {}; peak_working = peak_private = 0; min_available = available_mib()
    try:
        for job in jobs:
            folder = job["path"]
            commands = ["onerror {quit -code 2 -force}", "set started [clock milliseconds]",
                        f"run {duration_us} us", 'puts "BENCH_RUN_MS=[expr {[clock milliseconds]-$started}]"']
            if save_seed:
                commands += ["checkpoint -dir next_seed"]
            commands += ["quit -code 0 -force"]
            (folder / "run.do").write_text("\n".join(commands) + "\n")
            log = (folder / "console.log").open("wb")
            command = [str(MS / "vsim.exe"), "-batch", "-modelsimini", "modelsim.ini", "-l", "transcript.log",
                       "-restore", str(folder / "start.cpt"), "-do", "do run.do"]
            proc = subprocess.Popen(command, cwd=folder, env=env, stdout=log, stderr=subprocess.STDOUT)
            launched.append(dict(proc=proc, log=log, job=job, command=command))
        roots = {item["proc"].pid for item in launched}
        while True:
            table = children(); related = set(roots)
            while True:
                extra = {pid for pid, row in table.items() if row["parent"] in related}
                if extra <= related:
                    break
                related |= extra
            for pid in related:
                if pid not in handles:
                    h = K.OpenProcess(0x1000 | 0x400, False, pid)
                    if h:
                        handles[pid] = dict(handle=h, image=table.get(pid, {}).get("image", "exited"), cpu_seconds=0, peak_working=0, peak_private=0, faults=0)
            working = private = 0
            for item in handles.values():
                ts = [wintypes.FILETIME() for _ in range(4)]
                if K.GetProcessTimes(item["handle"], *(ctypes.byref(x) for x in ts)):
                    values = [(x.dwHighDateTime << 32) | x.dwLowDateTime for x in ts]
                    item["cpu_seconds"] = (values[2] + values[3]) / 10000000
                c = Counters(); c.size = ctypes.sizeof(c)
                if P.GetProcessMemoryInfo(item["handle"], ctypes.byref(c), c.size):
                    working += c.working; private += c.private
                    item.update(peak_working=max(item["peak_working"], c.peak_working),
                                peak_private=max(item["peak_private"], c.private), faults=max(item["faults"], c.faults))
            peak_working = max(peak_working, working); peak_private = max(peak_private, private)
            min_available = min(min_available, available_mib())
            if all(item["proc"].poll() is not None for item in launched):
                break
            if datetime.now(timezone.utc) >= stop_at or min_available < 256:
                raise RuntimeError("Experiment deadline or minimum-memory guard reached")
            time.sleep(0.5)
        elapsed = time.monotonic() - start
        results = []
        for item in launched:
            item["log"].close()
            folder = item["job"]["path"]; text = (folder / "console.log").read_text(errors="replace")
            if item["proc"].returncode != 0 or "** Error" in text or "** Fatal" in text:
                raise RuntimeError(f"Worker failed: {folder}, exit {item['proc'].returncode}")
            timing = re.search(r"BENCH_RUN_MS=(\d+)", text)
            if timing is None:
                raise RuntimeError(f"Missing run timing: {folder}")
            results.append(dict(name=item["job"]["name"], path=str(folder), command=item["command"],
                                simulation_run_ms=int(timing[1]), exit_code=item["proc"].returncode,
                                CSV_hashes={n: sha(folder / n) for n in CSV_NAMES},
                                run_do_sha256=sha(folder / "run.do"), transcript_sha256=sha(folder / "transcript.log")))
        return dict(wall_seconds=elapsed, cpu_seconds=sum(x["cpu_seconds"] for x in handles.values()),
                    peak_combined_working_MiB=peak_working / 1048576, peak_combined_private_MiB=peak_private / 1048576,
                    minimum_system_available_MiB=min_available,
                    processes=[{k: v for k, v in x.items() if k != "handle"} for x in handles.values()], workers=results)
    finally:
        for item in launched:
            if item["proc"].poll() is None:
                subprocess.run(["taskkill", "/PID", str(item["proc"].pid), "/T", "/F"], stdout=item["log"], stderr=subprocess.STDOUT)
                item["proc"].wait(timeout=30)
            if not item["log"].closed:
                item["log"].close()
        for item in handles.values():
            K.CloseHandle(item["handle"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stop-at", required=True)
    parser.add_argument("--duration-us", type=int, default=200)
    parser.add_argument("--prelude-us", type=int, default=1950)
    args = parser.parse_args()
    stop_at = datetime.fromisoformat(args.stop_at)
    if stop_at.tzinfo is None or args.duration_us <= 0 or args.prelude_us <= 0:
        raise ValueError("Explicit timezone and positive sample durations required")
    source = ROOT / "build/probes/submission_vo_cold_restore_001"
    cpt = source / "saved/vsim.cpt"
    reference = ROOT / "build/logs/submission_615a_013"
    original = ROOT / "build/logs/submission_615a_vo_002"
    old = json.loads((original / "summary.json").read_text())
    for name, digest in old["inputs"].items():
        if sha(Path(name)) != digest:
            raise ValueError(f"Original candidate input changed: {name}")
    if not json.loads((source / "proof.json").read_text())["all_five_CSVs_equal"]:
        raise ValueError("Seed cold restore not verified")
    protected = {str(source / n): sha(source / n) for n in CSV_NAMES + ("modelsim.ini", "saved/vsim.cpt")}
    golden = {p.name: sha(p) for p in (source / "golden").iterdir()}
    if golden != old["golden"]:
        raise ValueError("Seed Golden differs from original candidate")
    parent = ROOT / "build/probes"; i = 1
    while (parent / f"submission_vo_parallel_{i:03d}").exists():
        i += 1
    output = parent / f"submission_vo_parallel_{i:03d}"; output.mkdir()
    shutil.copy2(Path(__file__), output / Path(__file__).name)
    proof = dict(result="RUNNING", scope="two-process short interval performance experiment, not complete VO acceptance",
                 final_acceptance=False, started_utc=datetime.now(timezone.utc).isoformat(),
                 script_sha256=sha(Path(__file__)), VO_sha256=sha(original / "AFDX_top.vo"),
                 source_inputs=old["inputs"], source_checkpoint_sha256=sha(cpt), golden=golden,
                 duration_us=args.duration_us, prelude_us=args.prelude_us, clock_ns=8, resolution="1ps",
                 force_used=False, RTL_DUT_compiled=False, assertions_changed=False, background_acceptance_untouched=True)
    def save():
        (output / "summary.json").write_text(json.dumps(proof, indent=2) + "\n")
    save(); print(f"EXPERIMENT {output}", flush=True)
    try:
        seed_b = output / "seed_b"; clone(source, cpt, seed_b)
        print("PREPARING_SECOND_REAL_STATE", flush=True)
        proof["preparation"] = group([dict(name="seed_b", path=seed_b)], stop_at, args.prelude_us, save_seed=True)
        save()
        for name, src, cp in [("serial_a", source, cpt), ("serial_b", seed_b, seed_b / "next_seed/vsim.cpt"),
                              ("parallel_a", source, cpt), ("parallel_b", seed_b, seed_b / "next_seed/vsim.cpt")]:
            clone(src, cp, output / name)
        for name in ("serial_a", "serial_b"):
            print(f"MEASURING {name}", flush=True)
            proof[name] = group([dict(name=name, path=output / name)], stop_at, args.duration_us); save()
        print("MEASURING parallel_a + parallel_b", flush=True)
        proof["parallel"] = group([dict(name=n, path=output / n) for n in ("parallel_a", "parallel_b")], stop_at, args.duration_us)
        for name in ("a", "b"):
            serial = proof[f"serial_{name}"]["workers"][0]
            actual = next(x for x in proof["parallel"]["workers"] if x["name"] == f"parallel_{name}")
            if serial["CSV_hashes"] != actual["CSV_hashes"]:
                raise ValueError(f"Serial/parallel CSV mismatch: {name}")
        for name in ("serial_a", "serial_b", "parallel_a", "parallel_b"):
            for d in ("tx", "rx"):
                compare_prefix(complete_rows(output / name / f"wire_{d}.csv"), complete_rows(reference / f"wire_{d}.csv"), d)
        for name, digest in protected.items():
            if sha(Path(name)) != digest:
                raise ValueError(f"Historical seed changed: {name}")
        for name, digest in old["inputs"].items():
            if sha(Path(name)) != digest:
                raise ValueError(f"Active acceptance input changed: {name}")
        serial_seconds = proof["serial_a"]["wall_seconds"] + proof["serial_b"]["wall_seconds"]
        speedup = serial_seconds / proof["parallel"]["wall_seconds"]
        proof.update(result="BENCHMARK_MATCH_ONLY", serial_wall_seconds=serial_seconds,
                     parallel_wall_seconds=proof["parallel"]["wall_seconds"], two_worker_speedup=speedup,
                     two_worker_efficiency=speedup / 2,
                     conditional_workers_for_13h_to_4h=math.ceil(13 / 4 / (speedup / 2)),
                     conditional_workers_for_18h_to_3h=math.ceil(18 / 3 / (speedup / 2)),
                     CSVs_identical=True, RTL_Golden_wire_prefixes_match=True,
                     estimation_limit="Samples include early idle/protocol activity; scaling beyond two workers and long loaded intervals is not verified. Existing continuous nine-case chain is not partitioned by this experiment.")
    except Exception as exc:
        proof.update(result="EXPERIMENT_FAILED", error=f"{type(exc).__name__}: {exc}")
    proof["completed_utc"] = datetime.now(timezone.utc).isoformat(); save()
    print(json.dumps({k: v for k, v in proof.items() if k not in ("source_inputs", "preparation", "serial_a", "serial_b", "parallel", "golden")}), flush=True)
    return 0 if proof["result"] == "BENCHMARK_MATCH_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
