"""Explicit production file set; never compile both definitions of AFDX_top."""
from pathlib import Path
from prepare_stage2_mgmt_elinx import MGR_RTL

ROOT=Path(__file__).resolve().parents[1]
SUBMISSION_RTL=tuple(n for n in MGR_RTL if n not in (
    'afdx_stage2_mgmt_top.v','afdx_service_tx_arbiter.v','afdx_management_rx_demux.v'))+(
    'afdx_tftp_engine.v','afdx_atomic_file_store.v','afdx_615a_error_decoder.v',
    'afdx_615a_endpoint.v','afdx_load_message_fifo.v','afdx_management_rx_demux_615a.v',
    'afdx_service_tx_arbiter_615a.v','afdx_stage3_mgmt_top.v',
    'afdx_poll_timer.v','submission/AFDX_top.v')


def sources():
    return sorted((ROOT/'vendor/frozen').glob('*.v'))+[ROOT/'rtl'/n for n in SUBMISSION_RTL]


def core_sources():
    return [p for p in sources() if p.name not in ('AFDX_top.v','afdx_poll_timer.v')]
