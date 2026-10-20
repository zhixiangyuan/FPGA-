"""Independent per-VL integrity model; no RTL imports or simulated DUT values."""
from pathlib import Path
import json
import hashlib
import argparse

def generate(out):
    out.mkdir(parents=True, exist_ok=True)
    psn = {}
    rows = []
    enabled = [True] * 16
    def packet(vl, sn, length=9):
        previous = psn.get(vl)
        step = lambda n: 1 if n in (0, 255) else n + 1
        if not 0 <= vl < 16:
            decision, missing = 2, 0
        elif sn == 0:
            decision, missing = 3, 0
            psn[vl] = 0
        else:
            one = previous is not None and sn == step(previous)
            two = previous is not None and sn == step(step(previous))
            decision = 1 if previous is None or not enabled[vl] or one or two else 2
            missing = int(enabled[vl] and previous is not None and two)
            psn[vl] = sn
        rows.append([0, vl, sn, length, decision, missing, int(0 <= vl < 16 and enabled[vl])])
    # Interleave every VL: 256 ordinary frames per VL, including 255 -> 1.
    for n in range(256):
        for vl in range(16):
            packet(vl, n % 255 + 1, 1 + (n + vl) % 19)
    for vl in range(16):
        for sn in (3, 3, 2, 100, 101, 0, 1, 255, 1, 3):
            packet(vl, sn)
    packet(16, 5)
    packet(-1, 5)
    rows.append([1, 0, 0, 0, 0, 0, 0])
    psn.clear()
    for vl in range(16):
        packet(vl, 200)
        packet(vl, 201)
    # Disabling IC is a configured per-VL capability; SN0 remains control.
    enabled[7] = False
    packet(7, 50)
    packet(7, 50)
    packet(8, 50)
    (out / 'vectors.txt').write_text('\n'.join(' '.join(map(str,r)) for r in rows)+'\n')
    expected = {'vectors':len(rows), 'ordinary_wrap_frames_per_VL':256, 'VL_count':16,
                'scope':'SN gate only; complete retained and protocol-validated input required',
                'vectors_sha256':hashlib.sha256((out/'vectors.txt').read_bytes()).hexdigest()}
    (out / 'manifest.json').write_text(json.dumps(expected,indent=2)+'\n')
    return expected

if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    print(json.dumps(generate(parser.parse_args().out),indent=2))
