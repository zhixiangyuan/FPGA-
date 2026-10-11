"""Read-only simulator observation; writes only a separate monitor snapshot."""
from pathlib import Path
import json,subprocess,sys
from datetime import datetime,timezone
def main(run):
    now=datetime.now(timezone.utc);summary=json.loads((run/'summary.json').read_text())
    command="Get-Process -Name vsim,vsimk -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,CPU,StartTime | ConvertTo-Json -Compress"
    result=subprocess.run([r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe','-NoProfile','-Command',command],capture_output=True,text=True)
    procs=json.loads(result.stdout) if result.stdout.strip() else []
    if isinstance(procs,dict):procs=[procs]
    progress=(run/'frame_progress.csv').read_text().splitlines() if (run/'frame_progress.csv').exists() else []
    files={}
    for name in ('summary.json','provenance.json','frame_progress.csv','transcript.log','console.log','waves.wlf','actual_tx_gmii.csv','actual_payload.csv','sn_decisions.csv'):
        p=run/name
        if p.exists():
            st=p.stat();files[name]={'bytes':st.st_size,'mtime_utc':datetime.fromtimestamp(st.st_mtime,timezone.utc).isoformat()}
    monitor=run/'monitor';monitor.mkdir(exist_ok=True)
    old=sorted(monitor.glob('*.json'));previous=json.loads(old[-1].read_text()) if old else None
    snapshot={'observed_utc':now.isoformat(),'run':str(run),'result':summary['result'],'expected_modelsim_pid':summary.get('modelsim_pid'),'processes':procs,'last_frame_progress':progress[-1] if progress else None,'progress_rows':len(progress),'files':files,'writes_to_DUT_or_active_outputs':False}
    if previous:snapshot['previous_observed_utc']=previous['observed_utc'];snapshot['previous_progress']=previous['last_frame_progress']
    p=monitor/(now.strftime('%Y%m%dT%H%M%SZ')+'.json');p.write_text(json.dumps(snapshot,indent=2)+'\n')
    print(json.dumps(snapshot,indent=2))
if __name__=='__main__':main(Path(sys.argv[1]).resolve())
