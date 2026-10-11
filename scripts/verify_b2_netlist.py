"""Additional real-netlist provenance and independent BAG/frame audit."""
from pathlib import Path
import csv,hashlib,json,sys
from verify_b2_full import main as verify_full
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main(run):
    verify_full(run)
    summary=json.loads((run/'summary.json').read_text(encoding='utf-8'))
    provenance=json.loads((run/'provenance.json').read_text(encoding='utf-8'))
    assert not provenance['RTL_DUT_compiled'] and not provenance['force_used']
    assert provenance['clock_ns']==8 and provenance['BAG_cycles']==125000 and provenance['SN_wrap_frames']==256
    compiled=[Path(p) for p in provenance['compile_sources']]
    assert sorted(p.name for p in compiled)==sorted(['altera_primitives.v','220model.v','stratix_atoms.v','afdx_b2_synth_wrap.vo','tb_b2_netlist_protocol.sv'])
    exported=json.loads(Path(provenance['export_provenance']).read_text())
    assert exported['result']=='PASS' and exported['exit_code']==0 and not exported['synthesis_or_fit_executed']
    assert sha(run/'afdx_b2_synth_wrap.vo')==exported['delivered_netlist_sha256']
    assert 'B2_REAL_VO_NETLIST = PASS' in (run/'transcript.log').read_text()
    cases=json.loads((run/'golden/cases.json').read_text());byid={c['id']:c for c in cases}
    starts=[r for r in csv.DictReader((run/'actual_tx_gmii.csv').open(newline='')) if int(r['byte_index'])==0]
    assert len(starts)==263
    gaps=[];last=None;epoch=None
    for row in starts:
        c=byid[int(row['case_id'])];cycle=int(row['cycle'])
        if c['epoch']==epoch:
            assert cycle-last>=125000,(c,cycle,last)
            gaps.append(cycle-last)
        epoch=c['epoch'];last=cycle
    result=json.loads((run/'verification.json').read_text())
    assert result['gmii_bytes']==20454 and result['application_frames']==291 and result['application_bytes']==2431
    assert result['sn_decisions_compared']==303 and result['golden_cases']==309
    result.update(real_VO_provenance='PASS',independent_BAG_gaps_checked=len(gaps),minimum_BAG_cycles=min(gaps),diagnostic_addr_1='UNSUPPORTED',POST_SYNTH_TIMING='NOT VERIFIED',EQ6_NATIVE_NETLIST_EQUIVALENCE='NOT VERIFIED')
    (run/'netlist_verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main(Path(sys.argv[1]).resolve())
