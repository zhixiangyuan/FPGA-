"""Prepare an isolated EQ6HL45/CSG225 eLinx project and preflight its pins."""

from pathlib import Path
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
B0 = BASE / "stage5B0_selfmac_20261010"
B1 = BASE / "stage5B1_single_vl_20261010"
STAGE3 = BASE / "stage3B2_20261008"
CONSTRAINT = B0 / "evidence" / "gui_success_001" / "MacSelf" / "MacSelf.srcs" / "constrs_1" / "new" / "clock_125mhz.edc"
TOP = "afdx_b2_synth_wrap"

SOURCES = [
    (STAGE3 / "rtl" / "afdx_byte_fifo.v", "afdx_byte_fifo.v", "frozen stage3-B2 FIFO"),
    *[(B0 / "rtl" / n, n, "frozen B0 production RTL") for n in
      ("mac_crc32_byte.v", "mac_frame_store.v", "mac_gmii_tx.v", "mac_gmii_rx.v", "mac_gmii_core.v")],
    *[(B1 / "rtl" / n, n, "frozen B1 production RTL") for n in
      ("afdx_ipv4_checksum.v", "afdx_bag_gate.v", "afdx_single_vl_tx.v", "afdx_network_tx_top.v")],
    (ROOT / "rtl" / "afdx_single_vl_rx_candidate.v", "afdx_single_vl_rx_candidate.v", "frozen B2-1 parser"),
    (ROOT / "rtl" / "afdx_single_vl_sn_gate.v", "afdx_single_vl_sn_gate.v", "frozen B2-2 SN gate"),
    (ROOT / "rtl" / "afdx_protocol_rx_top.v", "afdx_protocol_rx_top.v", "frozen B2 protocol integration top"),
    (ROOT / "synth" / "afdx_b2_synth_wrap.v", "afdx_b2_synth_wrap.v", "B2-4 synthesis-only wrapper"),
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def port_budget(source: str) -> dict:
    header = source.split(");", 1)[0]
    ports = []
    for direction, left, right, name in re.findall(
        r"\b(input|output)\s+(?:wire|reg)\s*(?:\[(\d+):(\d+)\])?\s+([A-Za-z_]\w*)", header
    ):
        width = abs(int(left) - int(right)) + 1 if left else 1
        ports.append({"direction": direction, "name": name, "width": width})
    if not ports:
        raise ValueError("No top-level ports parsed")
    return {"input_bits": sum(p["width"] for p in ports if p["direction"] == "input"),
            "output_bits": sum(p["width"] for p in ports if p["direction"] == "output"),
            "total_bits": sum(p["width"] for p in ports), "ports": ports}


def main() -> int:
    frozen_b1 = json.loads((B1 / "B1_FREEZE_MANIFEST.json").read_text(encoding="utf-8"))
    frozen_b2 = json.loads((ROOT / "B2_EVIDENCE_MANIFEST.json").read_text(encoding="utf-8"))
    if not CONSTRAINT.is_file():
        raise FileNotFoundError(CONSTRAINT)
    if "create_clock -name gmii_clk -period 8.000" not in CONSTRAINT.read_text(encoding="utf-8-sig"):
        raise ValueError("Expected approved 8 ns clock constraint is missing")
    for original, _, _ in SOURCES:
        if not original.is_file():
            raise FileNotFoundError(original)
    b1_hashes = {e["path"]: e["sha256"] for e in frozen_b1["source"] + frozen_b1["frozen_dependencies"]}
    for original, _, owner in SOURCES:
        if owner.startswith("frozen B0") or owner.startswith("frozen B1") or owner.startswith("frozen stage3") or owner.startswith("frozen B2"):
            expected = b1_hashes.get(str(original))
            if expected is None and "B2" in owner:
                expected = next((e["sha256"] for e in frozen_b2["sources"] if e["path"] == str(original)), None)
            if expected is None or sha(original) != expected:
                raise ValueError(f"Frozen source hash mismatch: {original}")

    index = 1
    while (ROOT / "runs" / f"elinx_{index:03d}").exists():
        index += 1
    run = ROOT / "runs" / f"elinx_{index:03d}"
    project = run / "AFDXB2"
    source_dir = project / "AFDXB2.srcs" / "sources_1" / "new"
    constraint_dir = project / "AFDXB2.srcs" / "constrs_1" / "new"
    source_dir.mkdir(parents=True)
    constraint_dir.mkdir(parents=True)
    snapshots = []
    for original, name, owner in SOURCES:
        target = source_dir / name
        shutil.copy2(original, target)
        if sha(target) != sha(original):
            raise ValueError(f"Snapshot hash mismatch: {original}")
        snapshots.append({"original": str(original), "sha256": sha(original),
                          "snapshot": str(target), "snapshot_sha256": sha(target), "owner": owner})
    constraint = constraint_dir / "clock_125mhz.edc"
    shutil.copy2(CONSTRAINT, constraint)
    wrapper = (source_dir / "afdx_b2_synth_wrap.v").read_text(encoding="utf-8")
    budget = port_budget(wrapper)
    if budget["total_bits"] != 138:
        raise ValueError(f"Wrapper port budget changed; audited estimate was 138, actual={budget['total_bits']}")

    declared = set()
    bodies = []
    for _, name, _ in SOURCES:
        body = (source_dir / name).read_text(encoding="utf-8", errors="replace")
        declared.update(re.findall(r"\bmodule\s+([A-Za-z_$][A-Za-z0-9_$]*)\b", body))
        bodies.append(body)
    needed = {"afdx_b2_synth_wrap", "afdx_protocol_rx_top", "afdx_single_vl_sn_gate",
              "afdx_single_vl_rx_candidate", "afdx_network_tx_top", "afdx_single_vl_tx",
              "mac_gmii_core", "mac_gmii_tx", "mac_gmii_rx", "mac_frame_store",
              "mac_crc32_byte", "afdx_byte_fifo"}
    missing = sorted(needed - declared)
    if missing:
        raise ValueError(f"Required module definitions absent: {missing}")
    hierarchy = "\n".join(bodies)
    instantiations = {name: len(re.findall(rf"\b{name}\s*(?:#\s*\([^;]*?\))?\s+[A-Za-z_]\w*\s*\(", hierarchy, re.S))
                      for name in needed if name != "afdx_b2_synth_wrap"}
    for required in ("afdx_protocol_rx_top", "afdx_single_vl_sn_gate", "afdx_single_vl_rx_candidate",
                     "afdx_network_tx_top", "mac_gmii_core", "mac_gmii_rx", "mac_gmii_tx"):
        if instantiations.get(required, 0) < 1:
            raise ValueError(f"Required active hierarchy instance not found: {required}")

    epr = project / "AFDXB2.epr"
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
        '<!-- Independent B2-4 project. No Implementation/Bitstream run is defined. -->',
        '<Project Path="/AFDXB2.epr">','  <Configuration>',
        '    <Option Name="ActiveSimSet" Val=""/>','    <Option Name="Project Type" Val="RTL"/>',
        '    <Option Name="SimulationTopModule" Val=""/>','    <Option Name="Win_Version" Val="x86"/>',
        '  </Configuration>','  <FileSets>',
        '    <FileSet Name="sources_1" Type="DesignSrcs" RelSrcDir="$PSRCDIR/sources_1">']
    xml += [f'      <File Path="/AFDXB2.srcs/sources_1/new/{name}"/>' for _, name, _ in SOURCES]
    xml += ['    </FileSet>','    <FileSet Name="constrs_1" Type="Constrs" RelSrcDir="$PSRCDIR/constrs_1">',
        '      <File Path="/AFDXB2.srcs/constrs_1/new/clock_125mhz.edc"/>',
        '      <Config><Option Name="TargetConstrsFile" Val="/AFDXB2.srcs/constrs_1/new/clock_125mhz.edc"/></Config>',
        '    </FileSet>','  </FileSets>','  <Runs>',
        '    <Run Id="synth_1" Type="Synthesis" SrcSet="sources_1" ConstrsSet="constrs_1" State="current" Parent="" Configuration="">',
        '      <Option Id="Compilation Flow">Classic Flow</Option>','      <Option Id="Device">EQ6HL45</Option>',
        '      <Option Id="IPRepositories"></Option>','      <Option Id="LanguageVersion">VERILOG_2001</Option>',
        '      <Option Id="Package">CSG225</Option>','      <Option Id="Series">eHiChip6</Option>',
        '      <Option Id="TargetLanguage">VERILOG</Option>',f'      <Option Id="TopModule">{TOP}</Option>',
        '    </Run>','  </Runs>','  <PRFlow><PartitionDefs/><PRConfigurations/></PRFlow>','</Project>','']
    epr.write_text("\n".join(xml), encoding="utf-8")
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PREPARED_FOR_GUI_PREFLIGHT",
        "project_file": str(epr), "top_module": TOP,
        "device": "EQ6HL45", "package": "CSG225",
        "clock_constraint": str(constraint),
        "clock_constraint_text": constraint.read_text(encoding="utf-8-sig"),
        "top_port_budget": budget,
        "io_fit_status": "NOT VERIFIED; 138 estimate is not a package fit result",
        "sources": snapshots,
        "declared_modules": sorted(declared),
        "required_instance_counts_static_audit": instantiations,
        "logical_ram_bits_estimate": {"b0": 49152, "b2": 23536, "total": 72688},
        "timing_scope": "125 MHz internal clock constraint only; no Setup/Hold claim",
        "implementation_defined": False,
        "b0_b1_b2_frozen_sources_modified": False,
    }
    (run / "project_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("B2_ELINX_PREPARED", epr)
    print(f"B2_TOP={TOP} DEVICE=EQ6HL45 PACKAGE=CSG225 PORTS={budget['total_bits']} INPUT={budget['input_bits']} OUTPUT={budget['output_bits']}")
    print("STATIC_HIERARCHY_PREFLIGHT=PASS SOURCE_HASH_PREFLIGHT=PASS CLOCK=125MHz PERIOD=8ns")
    print("IMPLEMENTATION=NOT DEFINED; SYNTHESIS NOT RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
