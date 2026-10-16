#!/usr/bin/env python3
"""Generate structural wiring from the pinned KiCad connectivity export."""
import hashlib,json,re,sys
from pathlib import Path
R=Path(__file__).resolve().parent
source=R/'reference/connectivity.json';cs=json.loads(source.read_text())['components']
for c in cs.values():c['pins']={p:n.lstrip('/') if n else None for p,n in c['pins'].items()}
def net(s):return 'n_'+re.sub('[^a-zA-Z0-9_]','_',s)
used=['A1','A2.1','A2.2','A2.3','A4','A6'];names=sorted({n for c in cs.values() for n in c['pins'].values() if n})
lines=['// Generated from reference/connectivity.json SHA256 '+hashlib.sha256(source.read_bytes()).hexdigest(),'''module controller(input [15:0] address, input [7:0] cpu_data,
 input iorq_n, wr_n, input [103:0] contacts,
 output [7:0] read_data, output [1:0] leds,
 output ta_daten, ta_takt);
''']
lines+=['wire '+net(n)+';' for n in names]
lines+=['assign '+net('+5V')+"=1'b1;",'assign '+net('GND')+"=1'b0;"]
# Boundary terminals are discovered by actual CPU pin mapping, not repeated net names.
for i,p in enumerate([30,31,32,33,34,35,36,37,38,39,40,1,2,3,4,5]):lines+=['assign '+net(cs['A5']['pins'][str(p)])+f'=address[{i}];']
for i,p in enumerate([14,15,12,8,7,9,10,13]):
 n=net(cs['A5']['pins'][str(p)]);lines+=[f"assign {n}=!wr_n ? cpu_data[{i}] : 1'bz;",f'assign read_data[{i}]={n};',f'pullup({n});']
for p,v in [(20,'iorq_n'),(22,'wr_n')]:lines+=['assign '+net(cs['A5']['pins'][str(p)])+'='+v+';']
# Resistors to the supply are represented by Verilog pull strength, not active drives.
for ref,c in cs.items():
 pins=list(c['pins'].values())
 if ref.startswith('R') and len(pins)==2 and '+5V' in pins:
  lines+=['pullup('+net(next(n for n in pins if n!='+5V'))+');']
for i in range(13):lines+=[f'pullup({net("COL"+str(i))});']
# Analog row front end is a documented digital boundary. A low column with a
# closed contact drives its PNP collector high; multiple selected columns OR.
for i in range(8):lines+=['assign '+net('SENSE'+str(i))+'='+' | '.join(f'(contacts[{c*8+i}] && !{net("COL"+str(c))})' for c in range(13))+';']
for ref in used:
 c=cs[ref];ports=[]
 for p,n in sorted(c['pins'].items(),key=lambda a:int(a[0])):
  ports+=[f'.p{p}({net(n) if n else ""})']
 lines+=[f'chip_{c["type"]} '+ref.replace('.','_')+'('+','.join(ports)+');']
lines+=['assign leds={~'+net(cs['A6']['pins']['6'])+',~'+net(cs['A6']['pins']['8'])+'};','assign ta_daten='+net(cs['A1']['pins']['4'])+';','assign ta_takt='+net(cs['A1']['pins']['2'])+';','endmodule\n']
out=R/'generated/controller.v';text='\n'.join(lines)
if '--check' in sys.argv:
 if not out.exists() or out.read_text()!=text:raise SystemExit('Stale controller.v; run generate.py')
 print('HDL wiring matches pinned schematic connectivity')
else:out.write_text(text)
