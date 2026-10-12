"""Create read-only probes for the selected real V1 VO in a local build directory."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = Path(os.environ.get("AFDX_BUILD_ROOT", ROOT / "build"))
EVIDENCE_ROOT = Path(os.environ.get("AFDX_V1_EVIDENCE_ROOT", ROOT / "evidence"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vo", type=Path, default=EVIDENCE_ROOT / "eda_export_001" / "AFDX_top.vo")
    parser.add_argument("--output-dir", type=Path, default=BUILD_ROOT / "netlist_observer")
    args = parser.parse_args()
    vo = args.vo.resolve()
    if not vo.is_file():
        raise FileNotFoundError(f"Real AFDX_top.vo not found: {vo}")
    text = vo.read_text(encoding="utf-8", errors="replace")
    names = set(re.findall(r"\bwire\s*(?:\[[^\]]+\]\s*)?\\(\S+)\s*;", text))
    mapping = {
        "obs_psn": "protocol|sn_gate|psn",
        "obs_psn_valid": "protocol|sn_gate|psn_valid~regout",
        "obs_committed": "application|committed",
        "obs_app_busy": "application|busy",
        "obs_parser_busy": "protocol|rx_protocol|banks_busy",
        "obs_mac_busy0": "protocol|tx_mac|mac|rx|bank0|busy~regout",
        "obs_mac_busy1": "protocol|tx_mac|mac|rx|bank1|busy~regout",
    }
    widths = {"obs_psn": 8, "obs_committed": 2, "obs_app_busy": 2, "obs_parser_busy": 2}
    lines = ["// Read-only connections to actual exported wires. No RTL DUT or force."]
    for destination, source in mapping.items():
        if source not in names:
            raise RuntimeError(f"Preserved VO wire is missing: {source}")
        bits = f"[{widths[destination] - 1}:0] " if destination in widths else ""
        lines.append(f"wire {bits}{destination} = dut.\\{source} ;")
    for bank in (0, 1):
        for field, width in (("lengths", 11), ("origins", 8)):
            refs = []
            for bit in range(width - 1, -1, -1):
                name = f"application|{field}[{bank}][{bit}]~regout"
                if name not in names:
                    raise RuntimeError(f"Preserved VO register bit is missing: {name}")
                refs.append("dut.\\" + name + " ")
            lines.append(f"wire [{width - 1}:0] obs_{field}{bank} = " + "{" + ",".join(refs) + "};")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    observer = output_dir / "v1_netlist_observer.vh"
    observer.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {
        "VO": str(vo),
        "VO_sha256": sha(vo),
        "observer": str(observer),
        "observer_sha256": sha(observer),
        "mapped_wires": mapping,
        "application_metadata": "actual per-bit preserved lengths/origins register outputs",
        "DUT_driven": False,
        "force": False,
    }
    manifest_path = output_dir / "observer_mapping.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
