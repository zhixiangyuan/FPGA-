"""Bounded loaded-state VO scheduling study; never resumes official acceptance.

Restores private copies of the sealed real checkpoint. All stimuli, Golden,
clocks, timers and assertions remain those of the original compiled image.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time

import benchmark_submission_vo_parallel as monitor
from check_live_submission_vo import complete_rows, compare_prefix
from run_submission_vo_checkpoint import ROOT, MS, guard, work_hashes, sha

K = monitor.K
K.SetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.c_size_t]
K.GetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t)]
CSV = monitor.CSV_NAMES


def topology():
    f = K.GetSystemCpuSetInformation
    f.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.HANDLE, wintypes.DWORD]
    needed = wintypes.DWORD()
    f(None, 0, ctypes.byref(needed), None, 0)
    buffer = ctypes.create_string_buffer(needed.value)
    if not f(buffer, needed.value, ctypes.byref(needed), None, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    offset = 0; rows = []
    while offset < needed.value:
        size, kind = struct.unpack_from('<II', buffer.raw, offset)
        if size < 8:
            raise ValueError('Invalid CPU-set record')
        if kind == 0:
            ident, group, logical, core, cache, numa, efficiency, flags = struct.unpack_from('<IHBBBBBB', buffer.raw, offset + 8)
            rows.append(dict(id=ident, group=group, logical=logical, core=core,
                             efficiency_class=efficiency, flags=flags))
        offset += size
    return rows


def seal(run, summary):
    guard(run, summary)
    if summary['result'] != 'PAUSED':
        raise ValueError('Official run must remain PAUSED')
    checkpoint = summary['checkpoint']
    if work_hashes(run) != checkpoint['work_hashes']:
        raise ValueError('Official compiled cache changed')
    for name, digest in {**checkpoint['files'], **checkpoint['wire_artifacts']}.items():
        if sha(run / name) != digest:
            raise ValueError(f'Official checkpoint/output changed: {name}')


def measure(jobs, deadline, duration):
    if monitor.available_mib() < (1536 if len(jobs) > 1 else 1024):
        raise RuntimeError('Insufficient free memory for bounded experiment')
    env = os.environ.copy(); env.setdefault('MGLS_LICENSE_FILE', str(MS.parent / 'LICENSE.TXT'))
    launched = []; handles = {}; peak_working = peak_private = 0
    minimum = monitor.available_mib(); started = time.monotonic()
    try:
        for job in jobs:
            folder = job['path']
            lines = ['onerror {quit -code 2 -force}', 'set stamp [clock milliseconds]',
                     f'run {duration} us', 'puts "LOADED_RUN_MS=[expr {[clock milliseconds]-$stamp}]"',
                     'puts "LOADED_END_PS=$now"', 'checkpoint -dir next_seed', 'quit -code 0 -force']
            (folder / 'run.do').write_text('\n'.join(lines) + '\n')
            log = (folder / 'console.log').open('wb')
            command = [str(MS / 'vsim.exe'), '-batch', '-modelsimini', 'modelsim.ini', '-l', 'transcript.log',
                       '-restore', str(folder / 'start.cpt'), '-do', 'do run.do']
            process = subprocess.Popen(command, cwd=folder, env=env, stdout=log, stderr=subprocess.STDOUT)
            launched.append(dict(job=job, process=process, log=log))
        while True:
            table = monitor.children()
            for item in launched:
                related = {item['process'].pid}
                while True:
                    extra = {pid for pid, row in table.items() if row['parent'] in related}
                    if extra <= related:
                        break
                    related |= extra
                for pid in related:
                    if pid in handles:
                        continue
                    handle = K.OpenProcess(0x1000 | 0x400 | 0x200, False, pid)
                    if not handle:
                        continue
                    mask = item['job'].get('mask')
                    if mask and not K.SetProcessAffinityMask(handle, mask):
                        K.CloseHandle(handle)
                        raise ctypes.WinError(ctypes.get_last_error())
                    actual = ctypes.c_size_t(); system = ctypes.c_size_t()
                    if not K.GetProcessAffinityMask(handle, ctypes.byref(actual), ctypes.byref(system)):
                        K.CloseHandle(handle)
                        raise ctypes.WinError(ctypes.get_last_error())
                    handles[pid] = dict(handle=handle, name=item['job']['name'], image=table.get(pid, {}).get('image'),
                                        affinity_mask=actual.value, cpu_seconds=0)
            working = private = 0
            for item in handles.values():
                stamps = [wintypes.FILETIME() for _ in range(4)]
                if K.GetProcessTimes(item['handle'], *(ctypes.byref(x) for x in stamps)):
                    values = [(x.dwHighDateTime << 32) | x.dwLowDateTime for x in stamps]
                    item['cpu_seconds'] = (values[2] + values[3]) / 1e7
                counters = monitor.Counters(); counters.size = ctypes.sizeof(counters)
                if monitor.P.GetProcessMemoryInfo(item['handle'], ctypes.byref(counters), counters.size):
                    working += counters.working; private += counters.private
            peak_working = max(peak_working, working); peak_private = max(peak_private, private)
            minimum = min(minimum, monitor.available_mib())
            if all(item['process'].poll() is not None for item in launched):
                break
            if datetime.now(timezone.utc) >= deadline or minimum < 512:
                raise RuntimeError('Bounded experiment deadline or memory guard reached')
            time.sleep(.25)
        results = []
        for item in launched:
            item['log'].close(); folder = item['job']['path']
            console = (folder / 'console.log').read_text(errors='replace')
            transcript = (folder / 'transcript.log').read_text(errors='replace')
            if item['process'].returncode != 0 or any(x in console or x in transcript for x in ('** Error', '** Fatal')):
                raise ValueError(f"Sample failed: {folder}")
            timing = re.search(r'LOADED_RUN_MS=(\d+)', console)
            endpoint = re.search(r'LOADED_END_PS=(\d+)', console)
            if not timing or not endpoint or not (folder / 'next_seed/vsim.cpt').exists():
                raise ValueError(f'Missing timing/checkpoint: {folder}')
            results.append(dict(name=item['job']['name'], path=str(folder), mask=item['job'].get('mask'),
                                exit_code=item['process'].returncode, run_ms=int(timing[1]), end_ps=int(endpoint[1]),
                                CSV_hashes={n: sha(folder / n) for n in CSV},
                                checkpoint_sha256=sha(folder / 'next_seed/vsim.cpt'),
                                console_sha256=sha(folder / 'console.log'), transcript_sha256=sha(folder / 'transcript.log')))
        return dict(wall_seconds=time.monotonic() - started, workers=results,
                    peak_working_MiB=peak_working / 1048576, peak_private_MiB=peak_private / 1048576,
                    minimum_available_MiB=minimum, processes=[{k:v for k,v in row.items() if k != 'handle'} for row in handles.values()])
    finally:
        for item in launched:
            if item['process'].poll() is None:
                subprocess.run(['taskkill', '/PID', str(item['process'].pid), '/T', '/F'], stdout=item['log'], stderr=subprocess.STDOUT)
                item['process'].wait(timeout=30)
            if not item['log'].closed:
                item['log'].close()
        for item in handles.values():
            K.CloseHandle(item['handle'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stop-at', required=True)
    args = parser.parse_args(); deadline = datetime.fromisoformat(args.stop_at)
    if deadline.tzinfo is None:
        raise ValueError('Explicit deadline timezone required')
    run = ROOT / 'build/logs/submission_615a_vo_checkpoint_002'
    summary = json.loads((run / 'summary.json').read_text()); seal(run, summary)
    topology_rows = topology()
    for logical in (2, 4):
        if not any(x['logical'] == logical and x['group'] == 0 for x in topology_rows):
            raise ValueError(f'CPU {logical} unavailable')
    parent = ROOT / 'build/probes'; index = 1
    while (parent / f'vo_resume_optimization_{index:03d}').exists():
        index += 1
    output = parent / f'vo_resume_optimization_{index:03d}'; output.mkdir()
    shutil.copy2(__file__, output / Path(__file__).name)
    source_hash = sha(run / 'summary.json')
    result = dict(result='RUNNING', final_acceptance=False, started_utc=datetime.now(timezone.utc).isoformat(),
                  source_checkpoint=str(run / summary['checkpoint']['path']), source_checkpoint_sha256=sha(run / summary['checkpoint']['path']),
                  source_summary_sha256=source_hash, script_sha256=sha(Path(__file__)),
                  helper_sha256=sha(Path(monitor.__file__)), cpu_sets=topology_rows, duration_us=100,
                  clock_ns=8, BAG_cycles=125000, RTL_DUT_compiled=False, force_used=False, assertions_changed=False,
                  source_inputs=summary['inputs'], golden=summary['golden'], phases={})
    def save():
        temporary = output / 'summary.tmp'
        temporary.write_text(json.dumps(result, indent=2) + '\n');temporary.replace(output / 'summary.json')
    def execute(name, source, checkpoint, mask=None):
        folder = output / name; monitor.clone(source, checkpoint, folder)
        return dict(name=name, path=folder, mask=mask)
    def phase(name, jobs):
        print(name, flush=True)
        value = measure(jobs, deadline, 100); result['phases'][name] = value; save()
        reference = Path(summary['reference_RTL_run'])
        for worker in value['workers']:
            folder = Path(worker['path'])
            if {p.name:sha(p) for p in (folder / 'golden').iterdir()} != summary['golden']:
                raise ValueError('Sample Golden changed')
            for direction in ('tx','rx'):
                compare_prefix(complete_rows(folder / f'wire_{direction}.csv'), complete_rows(reference / f'wire_{direction}.csv'), direction)
        return value
    save(); print(str(output), flush=True)
    try:
        cpt = run / summary['checkpoint']['path']
        phase('default_a', [execute('default_a', run, cpt)])
        state_b = output / 'default_a'; cpt_b = state_b / 'next_seed/vsim.cpt'
        phase('default_b', [execute('default_b', state_b, cpt_b)])
        phase('cpu2_a', [execute('cpu2_a', run, cpt, 1 << 2)])
        phase('cpu4_b', [execute('cpu4_b', state_b, cpt_b, 1 << 4)])
        phase('default_a_repeat', [execute('default_a_repeat', run, cpt)])
        phase('cpu2_a_repeat', [execute('cpu2_a_repeat', run, cpt, 1 << 2)])
        phase('parallel_default', [execute('parallel_default_a', run, cpt), execute('parallel_default_b', state_b, cpt_b)])
        phase('parallel_pinned', [execute('parallel_pinned_a', run, cpt, 1 << 2), execute('parallel_pinned_b', state_b, cpt_b, 1 << 4)])
        for name, record in result['phases'].items():
            for worker in record['workers']:
                interval = 'a' if worker['name'].endswith('_a') or '_a_' in worker['name'] else 'b'
                baseline = result['phases']['default_' + interval]['workers'][0]
                if worker['CSV_hashes'] != baseline['CSV_hashes'] or worker['end_ps'] != baseline['end_ps']:
                    raise ValueError(f"Loaded sample differs from original interval: {worker['name']}")
                if worker['mask']:
                    kernels = [p for p in record['processes'] if p['name'] == worker['name'] and p['image'] == 'vsimk.exe']
                    if not kernels or any(p['affinity_mask'] != worker['mask'] for p in kernels):
                        raise ValueError('Kernel affinity not verified')
        seal(run, summary)
        if sha(run / 'summary.json') != source_hash:
            raise ValueError('Official summary changed')
        result.update(result='LOADED_BENCHMARK_MATCH_ONLY', original_run_unchanged=True,
                      note='Adjacent 100us real-state intervals only. Parallel replay does not partition the original continuous nine-case critical path.')
    except Exception as error:
        result.update(result='EXPERIMENT_FAILED', error=f'{type(error).__name__}: {error}')
    result['completed_utc'] = datetime.now(timezone.utc).isoformat(); save()
    print(json.dumps({k:v for k,v in result.items() if k not in ('source_inputs','golden','cpu_sets','phases')}), flush=True)
    return 0 if result['result'] == 'LOADED_BENCHMARK_MATCH_ONLY' else 1


if __name__ == '__main__':
    raise SystemExit(main())
