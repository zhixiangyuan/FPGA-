"""Report top-level nets that more than one module output drives.

The management-service integration once failed because two module outputs
shared one top-level net. The two driven values resolved to X, a downstream
legality expression became unknown, and the frame builder silently dropped a
descriptor. Verilog allows this wiring, so it is checked statically here.
"""
from collections import defaultdict
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"//[^\n]*", " ", text)


def port_directions(header):
    """Map port name to direction for one module header."""
    directions = {}
    current = None
    for piece in header.split(","):
        match = re.search(r"\b(input|output|inout)\b", piece)
        if match:
            current = match.group(1)
            piece = piece[match.end():]
        if current is None:
            continue
        piece = re.sub(r"\b(wire|reg|logic|signed|unsigned)\b", " ", piece)
        piece = re.sub(r"\[[^\]]*\]", " ", piece)
        piece = re.sub(r"=.*", " ", piece)
        for name in re.findall(r"[A-Za-z_]\w*", piece):
            directions.setdefault(name, current)
    return directions


def module_signatures(text):
    signatures = {}
    for match in re.finditer(r"\bmodule\s+(\w+)\b(.*?)\bendmodule\b", text, flags=re.S):
        body = match.group(2)
        head = body[:body.find(";") + 1] if ";" in body else body
        signatures[match.group(1)] = port_directions(head)
    return signatures


INSTANCE = re.compile(r"\b(\w+)\s*(?:#\s*\((?:[^()]|\([^()]*\))*\))?\s*(\w+)\s*\(((?:[^()]|\([^()]*\))*)\)\s*;", re.S)


def instances(text, known):
    for match in INSTANCE.finditer(text):
        name, label, connections = match.group(1), match.group(2), match.group(3)
        if name not in known:
            continue
        ports = re.findall(r"\.\s*(\w+)\s*\(\s*([^)]*?)\s*\)", connections)
        yield name, label, ports


def is_net(value):
    if not value or "'" in value or value.startswith("{") or value.startswith("("):
        return False
    return re.fullmatch(r"[A-Za-z_]\w*(\s*\[\s*[\w:+-]+\s*\])?", value) is not None


def collect(text, known):
    drivers = defaultdict(list)
    count = 0
    for name, label, ports in instances(text, known):
        count += 1
        for port, value in ports:
            if not is_net(value):
                continue
            if known[name].get(port) in ("output", "inout"):
                drivers[value].append(f"{name} {label} .{port}")
    return count, {net: who for net, who in drivers.items() if len(who) > 1}


def self_test():
    sample = ("module leaf_a(output wire [7:0] d, input wire clk); endmodule "
              "module leaf_b(output wire [7:0] d); endmodule "
              "module top(input wire clk); wire [7:0] shared; "
              "leaf_a u_a(.clk(clk),.d(shared)); leaf_b u_b(.d(shared)); endmodule")
    known = module_signatures(sample)
    _, conflicts = collect(sample, known)
    assert sorted(conflicts) == ["shared"], conflicts
    assert len(conflicts["shared"]) == 2, conflicts


def main():
    self_test()
    sources = list((ROOT / "rtl").glob("*.v")) + list((ROOT / "vendor/frozen").glob("*.v"))
    known = {}
    for path in sources:
        known.update(module_signatures(strip_comments(path.read_text(encoding="utf-8", errors="replace"))))
    tops = [Path(a) if Path(a).is_absolute() else ROOT / a for a in sys.argv[1:]] or [
        ROOT / "rtl/afdx_stage2_top.v", ROOT / "rtl/afdx_stage2_mgmt_top.v", ROOT / "rtl/AFDX_top.v",
        ROOT / "rtl/submission/AFDX_top.v"]
    failed = 0
    for top in tops:
        count, conflicts = collect(strip_comments(top.read_text(encoding="utf-8", errors="replace")), known)
        print(f"TOP_DRIVER_CHECK {top.name} instances={count} multi_driver={len(conflicts)}")
        for net, who in sorted(conflicts.items()):
            print(f"  MULTI_DRIVER net={net}: " + "; ".join(sorted(who)))
        failed += len(conflicts)
    print("TOP_DRIVER_CHECK_RESULT " + ("PASS" if not failed else "FAIL"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())