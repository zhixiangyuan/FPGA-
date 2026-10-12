"""Continue approved stage1 closure automatically after the sole live VO run."""
from pathlib import Path
import json,subprocess,sys,time
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
def main():
 control=ROOT/'runs/system_extension_001';control.mkdir(exist_ok=True)
 lock=control/'closure_worker.lock'
 with lock.open('x') as f:f.write(str(__import__('os').getpid()))
 try:
  until=time.monotonic()+86400
  while time.monotonic()<until:
   s=json.loads((ROOT/'runs/netlist_001/summary.json').read_text())
   if s['result'] not in ('PREPARING','RUNNING') and not (ROOT/'runs/V1_NETLIST_RUNNING.lock').exists():break
   time.sleep(20)
  else:raise TimeoutError('VO completion waiting deadline')
  if s['result']!='PASS':raise RuntimeError('VO result '+s['result']+'; preserve evidence for agent diagnosis')
  for name in ('finish_v1_system.py','archive_v1_system.py'):
   with (control/(name+'.log')).open('wb') as log:
    r=subprocess.run([sys.executable,str(ROOT/'scripts'/name)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
   if r.returncode:raise RuntimeError(name+' failed; preserve evidence and continue diagnosis')
  (control/'closure_status.json').write_text(json.dumps({'result':'COMPLETE_AWAITING_CAPTAIN_REVIEW','completed_utc':datetime.now(timezone.utc).isoformat(),'stage2':'NOT RUN'},indent=2)+'\n')
  print('STAGE1_AUTONOMOUS_CLOSURE COMPLETE',flush=True)
 except Exception as e:
  (control/'closure_status.json').write_text(json.dumps({'result':'NEEDS_DIAGNOSIS','error':repr(e),'time_utc':datetime.now(timezone.utc).isoformat()},indent=2)+'\n');raise
 finally:
  lock.replace(control/'closure_worker_closed.lock')
if __name__=='__main__':main()
