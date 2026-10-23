#!/usr/bin/env python3
"""Review switching-event evidence without promoting diagnostic runs."""
import argparse,hashlib,json,lzma,re
from pathlib import Path
from live_cap_review import assess
from live_prefix_review import compare

def review(root):
 log=lzma.decompress((root/'live-cap-capture/ngspice.log.xz').read_bytes()).decode()
 first,last=assess(log),assess(log,True)
 edges=[];samples=[]
 for name in ('live-edges25','live-edges12'):
  path=root/name;r=json.loads((path/'run.json').read_text())
  if r['timedOut'] or r['solverDiagnostic']:raise ValueError('Incomplete edge control')
  text=lzma.decompress((path/'ngspice.log.xz').read_bytes()).decode()
  edges.append([int(t) for t in re.findall(r'BUS_EDGE_PS (\d+)',text)])
  samples.append([s.split()[2:] for s in re.findall(r'BUS_SAMPLE [^\n]+',text)])
 if not edges[0] or len(edges[0])!=len(edges[1]) or samples[0]!=samples[1]:raise ValueError('Firmware sequence differs')
 controls={}
 for path in sorted(root.glob('*/run.json')):
  r=json.loads(path.read_text());controls[path.parent.name]={key:r.get(key) for key in ('timedOut','solverDiagnostic','stepNs','toleranceScale','fixtureCrossingGuardPs','mpfrStartNs','method')}
 return {'qualified':False,'firstRejection':first,'terminalCollapse':last,
         'edgeTimesPs':edges,'maximumEdgeDifferencePs':max(abs(a-b) for a,b in zip(*edges)),
         'prefixComparison':compare([root/n/'witness.txt.xz' for n in ('live-edges25','live-edges12')]),
         'controls':controls,'boundary':'Clock crossings are analytical controls for the ideal fixture only; sampled ADC timing is not generally corrected. Constant-capacitor assembly replay leaves other devices and histories fixed. Full runs and tighter tolerances do not converge.'}

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--verify',action='store_true');a=p.parse_args();result=review(a.root);path=a.root/'assessment.json'
 if a.verify:
  if result!=json.loads(path.read_text()):raise ValueError('Retained review differs')
 else:path.write_text(json.dumps(result,indent=2)+'\n')
