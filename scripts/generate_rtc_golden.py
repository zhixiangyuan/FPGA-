"""Integer-rational NTP clock and four-timestamp reference vectors."""
from pathlib import Path
import json
INITIAL=0xe900000000000000
HZ=125000000
MASK=(1<<64)-1
def signed(v):
 v&=MASK
 return v-(1<<64) if v>>63 else v
def generate(out):
 out.mkdir(parents=True,exist_ok=True)
 vectors=[]
 for cycles in (1,10,125,125000,1250000):vectors.append([0,cycles,0,0,0,0,0])
 base=INITIAL
 def exchange(offset,half_delay,work):
  return [1,1,base,(base+offset+half_delay)&MASK,(base+offset+half_delay+work)&MASK,(base+2*half_delay+work)&MASK,0]
 vectors += [exchange(1<<28,1<<20,1<<18),exchange(-(1<<27),1<<20,1<<18),exchange(1,1,0)]
 vectors += [[1,1,0,base,base,base,0], [1,1,base,base+10,base+5,base+20,0],
             [1,1,base,base,0,base+100,0], [1,1,base,base,base,base+(2<<32),0]]
 # NTP era wrap: modular arithmetic still gives the correct bounded interval.
 vectors += [[1,1,MASK-100,50,80,120,0],exchange(-(1<<25),1<<12,1<<10)]
 reference=[]
 for row in vectors:
  kind,cycles,t1,t2,t3,t4,_=row
  n=signed(t4-t1);s=signed(t3-t2);delay=n-s
  valid=kind==1 and t1!=0 and t3!=0 and n>=0 and s>=0 and 0<=delay<=1<<32
  offset=(signed(t2-t1)+signed(t3-t4))//2
  row[-1]=int(valid)
  reference.append({'kind':kind,'cycles':cycles,'timestamps':[t1,t2,t3,t4],
                    'valid':bool(valid),'offset':offset,'delay':delay})
 (out/'vectors.txt').write_text('\n'.join(f'{r[0]} {r[1]} '+ ' '.join(f'{v:016x}' for v in r[2:6])+f' {r[6]}' for r in vectors)+'\n')
 (out/'reference.json').write_text(json.dumps(reference,indent=2)+'\n')
 return reference
