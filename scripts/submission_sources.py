"""Explicit production file set; never compile both definitions of AFDX_top."""
from pathlib import Path
from prepare_stage2_mgmt_elinx import MGR_RTL

ROOT=Path(__file__).resolve().parents[1]
SUBMISSION_RTL=MGR_RTL+('afdx_poll_timer.v','submission/AFDX_top.v')


def sources():
    return sorted((ROOT/'vendor/frozen').glob('*.v'))+[ROOT/'rtl'/n for n in SUBMISSION_RTL]
