from pathlib import Path
import hashlib
import json
import shutil
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
B0 = Path(r"D:\FPGA\captain_integration\stage5B0_selfmac_20261010")
CONSTRAINT = B0 / "evidence" / "gui_success_001" / "MacSelf" / "MacSelf.srcs" / "constrs_1" / "new" / "clock_125mhz.edc"

SOURCES = [
    (B0 / "deps" / "afdx_byte_fifo.v", "afdx_byte_fifo.v"),
    (B0 / "rtl" / "mac_crc32_byte.v", "mac_crc32_byte.v"),
    (B0 / "rtl" / "mac_frame_store.v", "mac_frame_store.v"),
    (B0 / "rtl" / "mac_gmii_tx.v", "mac_gmii_tx.v"),
    (B0 / "rtl" / "mac_gmii_rx.v", "mac_gmii_rx.v"),
    (B0 / "rtl" / "mac_gmii_core.v", "mac_gmii_core.v"),
    (ROOT / "rtl" / "afdx_ipv4_checksum.v", "afdx_ipv4_checksum.v"),
    (ROOT / "rtl" / "afdx_bag_gate.v", "afdx_bag_gate.v"),
    (ROOT / "rtl" / "afdx_single_vl_tx.v", "afdx_single_vl_tx.v"),
    (ROOT / "rtl" / "afdx_network_tx_top.v", "afdx_network_tx_top.v"),
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    i = 1
    while (ROOT / "runs" / f"elinx_{i:03d}").exists():
        i += 1
    run = ROOT / "runs" / f"elinx_{i:03d}"
    project = run / "AFDXNetwork"
    source_dir = project / "AFDXNetwork.srcs" / "sources_1" / "new"
    constraint_dir = project / "AFDXNetwork.srcs" / "constrs_1" / "new"
    source_dir.mkdir(parents=True)
    constraint_dir.mkdir(parents=True)
    records = []
    for original, name in SOURCES:
        if not original.is_file():
            raise FileNotFoundError(original)
        target = source_dir / name
        shutil.copy2(original, target)
        records.append({
            "original": str(original),
            "original_sha256": sha(original),
            "snapshot": str(target),
            "snapshot_sha256": sha(target),
            "owner": "B0 production dependency" if "stage5B0_selfmac" in str(original) else "new B1 production RTL",
        })
    if not CONSTRAINT.is_file():
        raise FileNotFoundError(CONSTRAINT)
    constr = constraint_dir / "clock_125mhz.edc"
    shutil.copy2(CONSTRAINT, constr)

    epr = project / "AFDXNetwork.epr"
    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!-- B1 independent project shell, based on the installed eLinx GUI project schema. -->',
        '<Project Path="/AFDXNetwork.epr">',
        '  <Configuration>',
        '    <Option Name="ActiveSimSet" Val=""/>',
        '    <Option Name="Project Type" Val="RTL"/>',
        '    <Option Name="SimulationTopModule" Val=""/>',
        '    <Option Name="Win_Version" Val="x86"/>',
        '  </Configuration>',
        '  <FileSets>',
        '    <FileSet Name="sources_1" Type="DesignSrcs" RelSrcDir="$PSRCDIR/sources_1">',
    ]
    xml.extend(f'      <File Path="/AFDXNetwork.srcs/sources_1/new/{name}"/>' for _, name in SOURCES)
    xml.extend([
        '    </FileSet>',
        '    <FileSet Name="constrs_1" Type="Constrs" RelSrcDir="$PSRCDIR/constrs_1">',
        '      <File Path="/AFDXNetwork.srcs/constrs_1/new/clock_125mhz.edc"/>',
        '      <Config><Option Name="TargetConstrsFile" Val="/AFDXNetwork.srcs/constrs_1/new/clock_125mhz.edc"/></Config>',
        '    </FileSet>',
        '  </FileSets>',
        '  <Runs>',
        '    <Run Id="synth_1" Type="Synthesis" SrcSet="sources_1" ConstrsSet="constrs_1" State="current" Parent="" Configuration="">',
        '      <Option Id="Compilation Flow">Classic Flow</Option>',
        '      <Option Id="Device">EQ6HL45</Option>',
        '      <Option Id="IPRepositories"></Option>',
        '      <Option Id="LanguageVersion">VERILOG_2001</Option>',
        '      <Option Id="Package">CSG225</Option>',
        '      <Option Id="Series">eHiChip6</Option>',
        '      <Option Id="TargetLanguage">VERILOG</Option>',
        '      <Option Id="TopModule">afdx_network_tx_top</Option>',
        '    </Run>',
        '  </Runs>',
        '  <PRFlow><PartitionDefs/><PRConfigurations/></PRFlow>',
        '</Project>',
        '',
    ])
    epr.write_text("\n".join(xml), encoding="utf-8")

    summary = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PREPARED_FOR_OFFICIAL_GUI_SYNTHESIS",
        "project_file": str(epr),
        "top_module": "afdx_network_tx_top",
        "device": "EQ6HL45",
        "package": "CSG225",
        "constraint_path": str(constr),
        "constraint_text": constr.read_text(encoding="utf-8-sig"),
        "constraint_scope": "125 MHz internal clock only; no external input/output delay budget; no timing-pass claim",
        "all_sources_are_independent_snapshots": True,
        "source_manifest": records,
        "b0_sources_modified": False,
        "implementation_run_created": False,
    }
    (run / "project_manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("ELINX_PROJECT_PREPARED", epr)
    print("ELINX_TOP=afdx_network_tx_top DEVICE=EQ6HL45 PACKAGE=CSG225 CLOCK=125MHz PERIOD=8ns")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
