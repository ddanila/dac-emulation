#!/usr/bin/env python3
"""Generate structural wiring from the pinned KiCad connectivity export."""
import hashlib,json,re,sys
from pathlib import Path
R=Path(__file__).resolve().parent
source=R/'reference/connectivity.json';cs=json.loads(source.read_text())['components']
pin=json.loads((R/'reference/source.json').read_text())
if hashlib.sha256(source.read_bytes()).hexdigest()!=pin['sha256']:raise SystemExit('Connectivity does not match pinned CAD source; use sync_reference.py')
for c in cs.values():c['pins']={p:n.lstrip('/') if n else None for p,n in c['pins'].items()}
def net(s):return 'n_'+re.sub('[^a-zA-Z0-9_]','_',s)
used=['A1','A2.1','A2.2','A2.3','A4','A6'];names=sorted({n for c in cs.values() for n in c['pins'].values() if n})
if len({net(n) for n in names})!=len(names):raise SystemExit('Net names collide after HDL identifier conversion')
if {r for r in cs if r.startswith('A')}-set(used)-{'A5','A7','A8'}:raise SystemExit('Unclassified digital component: extend the model or explicit boundaries')
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
# Bridge topology comes from the same numbered schematic pins. Analog sources
# remain boundary inputs; opening a bridge enables independent CPU-side stimulus.
service=['module controller_service(input oscillator, reset_source_n, br1_closed, br2_closed,',
 ' input external_clk, external_reset_n, output cpu_clk, cpu_reset_n);']
service_nets={cs[r]['pins'][p] for r,p in [('BR1','1'),('BR1','2'),('BR2','1'),('BR2','2'),('A5','6'),('A5','26'),('A7','8'),('V4.9','C')]}
service+=['wire '+net(n)+';'for n in sorted(service_nets)]
for ref,pin,value in [('A7','8','oscillator'),('V4.9','C','reset_source_n')]:service+=['assign '+net(cs[ref]['pins'][pin])+'='+value+';']
for ref,control in [('BR1','br1_closed'),('BR2','br2_closed')]:
 service+=['tranif1 '+ref+'('+','.join(net(cs[ref]['pins'][p])for p in ['1','2'])+','+control+');']
for pin,external,output in [('6','external_clk','cpu_clk'),('26','external_reset_n','cpu_reset_n')]:
 n=net(cs['A5']['pins'][pin]);service+=[f'assign {n}={external};',f'assign {output}={n};']
for ref,c in cs.items():
 pins=list(c['pins'].values())
 if ref.startswith('R') and len(pins)==2 and '+5V'in pins:
  other=next(n for n in pins if n!='+5V')
  if other in service_nets:service+=['pullup('+net(other)+');']
service+=['endmodule\n']
out=R/'generated/controller.v';text='\n'.join(lines+service)
if '--check' in sys.argv:
 if not out.exists() or out.read_text()!=text:raise SystemExit('Stale controller.v; run generate.py')
 print('HDL wiring matches pinned schematic connectivity')
else:out.write_text(text)
