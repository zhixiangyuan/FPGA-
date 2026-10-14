"""Generate an ignored eLinx project from the canonical, hash-checked sources."""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = Path(os.environ.get("AFDX_BUILD_ROOT", ROOT / "build"))
TEMPLATE = ROOT / "elinx" / "AFDXV1"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    template_epr = TEMPLATE / "AFDXV1.epr"
    template_edc = TEMPLATE / "AFDXV1.srcs" / "constrs_1" / "new" / "clock_125mhz.edc"
    if not template_epr.is_file() or not template_edc.is_file():
        raise FileNotFoundError("Tracked eLinx EPR template or 8 ns EDC is missing")

    # V1 is a sealed integration profile. Development modules in rtl/ must
    # not silently enter its source set or invalidate the 16-source template.
    sources = sorted((ROOT / "vendor" / "frozen").glob("*.v")) + [
        ROOT / "rtl" / name for name in
        ("AFDX_top.v", "afdx_app_echo_queue.v", "afdx_gmii_candidate_boundary.v")]
    names = [p.name for p in sources]
    if len(sources) != 16 or len(set(names)) != len(names):
        raise RuntimeError(f"Expected 16 uniquely named canonical Verilog sources; found {len(sources)}")

    projects = BUILD_ROOT / "elinx"
    projects.mkdir(parents=True, exist_ok=True)
    index = 1
    while (projects / f"AFDXV1_{index:03d}").exists():
        index += 1
    project = projects / f"AFDXV1_{index:03d}"
    shutil.copytree(TEMPLATE, project)

    source_dir = project / "AFDXV1.srcs" / "sources_1" / "new"
    source_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for source in sources:
        snapshot = source_dir / source.name
        shutil.copy2(source, snapshot)
        source_hash = sha(source)
        snapshot_hash = sha(snapshot)
        if source_hash != snapshot_hash:
            raise RuntimeError(f"Source copy hash mismatch: {source.name}")
        rows.append({"canonical_source": source.relative_to(ROOT).as_posix(),
                     "snapshot": snapshot.relative_to(project).as_posix(),
                     "sha256": source_hash, "snapshot_sha256": snapshot_hash})

    constraint = project / "AFDXV1.srcs" / "constrs_1" / "new" / "clock_125mhz.edc"
    shutil.copy2(template_edc, constraint)
    epr = (project / "AFDXV1.epr").read_text(encoding="utf-8")
    declared = re.findall(r'<File Path="/AFDXV1\.srcs/sources_1/new/([^"]+)"', epr)
    if sorted(declared) != sorted(names):
        raise RuntimeError("EPR source list does not match the canonical RTL set")
    if "EQ6HL45" not in epr or "CSG225" not in epr or "AFDX_top" not in epr:
        raise RuntimeError("EPR target or top module differs from the approved V1.0 project")
    if "-period 8.000" not in constraint.read_text(encoding="utf-8"):
        raise RuntimeError("The copied EDC does not specify the 8 ns clock")

    header = (ROOT / "rtl" / "AFDX_top.v").read_text(encoding="utf-8").split(");", 1)[0]
    ports = re.findall(r"\b(input|output)\s+wire\s*(?:\[(\d+):(\d+)\])?\s+(\w+)", header)
    port_bits = sum(abs(int(a) - int(b)) + 1 if a else 1 for _, a, b, _ in ports)
    if len(ports) != 8 or port_bits != 22:
        raise RuntimeError(f"Unexpected candidate interface: {len(ports)} ports, {port_bits} bits")

    manifest = {
        "status": "PREPARED_NOT_SYNTHESIZED",
        "project": str(project / "AFDXV1.epr"),
        "top": "AFDX_top",
        "device": "EQ6HL45",
        "package": "CSG225",
        "clock_constraint_ns": 8,
        "ports": 8,
        "io_bits": port_bits,
        "sources": rows,
        "constraint_sha256": sha(constraint),
        "frozen_core_manifest_sha256": sha(ROOT / "FROZEN_CORE_MANIFEST.json"),
        "production_rtl_modified": False,
        "Implementation": "NOT RUN",
        "Bitstream": "NOT RUN",
        "POST_SYNTH_TIMING": "NOT VERIFIED",
        "EQ6_NATIVE_NETLIST_EQUIVALENCE": "NOT VERIFIED",
        "physical_IO_fit": "NOT VERIFIED",
    }
    (project / "project_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
