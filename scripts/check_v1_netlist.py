"""Read-only simulator/progress check; only writes separate monitor records."""
from pathlib import Path
import json,subprocess,sys
from datetime import datetime,timezone
def main(run):
 now=datetime.now(timezone.utc);s=json.loads((run/'summary.json').read_text())
 ps=subprocess.run([r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe','-NoProfile','-Command','Get-Process -Name vsim,vsimk -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,CPU,StartTime | ConvertTo-Json -Compress'],capture_output=True,text=True)
 procs=json.loads(ps.stdout) if ps.stdout.strip() else []
 if isinstance(procs,dict):procs=[procs]
 rows=(run/'frame_progress.csv').read_text().splitlines() if (run/'frame_progress.csv').exists() else []
 files={}
 for n in ('summary.json','provenance.json','frame_progress.csv','actual_tx.csv','app_commits.csv','input_events.csv','decisions.csv','waves.wlf','transcript.log','console.log'):
  p=run/n
  if p.exists():st=p.stat();files[n]={'bytes':st.st_size,'mtime_utc':datetime.fromtimestamp(st.st_mtime,timezone.utc).isoformat()}
 mon=run/'monitor';mon.mkdir(exist_ok=True);old=sorted(mon.glob('*.json'));previous=json.loads(old[-1].read_text()) if old else None
 record={'observed_utc':now.isoformat(),'result':s['result'],'expected_vsim_pid':s.get('modelsim_pid'),'processes':procs,'last_progress':rows[-1] if rows else None,'rows':len(rows),'files':files,'DUT_or_live_outputs_written':False}
 if previous:record['previous_time']=previous['observed_utc'];record['previous_progress']=previous['last_progress']
 (mon/(now.strftime('%Y%m%dT%H%M%SZ')+'.json')).write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))
if __name__=='__main__':main(Path(sys.argv[1]).resolve())
