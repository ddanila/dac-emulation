from pathlib import Path
import json,sys,re,math,hashlib
sys.path.insert(0,str(Path('verification/robotron-keyboard/analog').resolve()))
from raw_waveform import header,rows
root=Path('build/keyboard-controller-analog/clock-crossing-control-v2')
r=json.loads((root/'assessment.json').read_text());results=[]
edges=[(t*1e-9,level) for cycle in range(1109) for t,level in ((511.28+cycle*1000,1),(1011.72+cycle*1000,0))]
for run in r['runs']:
 folder=root/f'{"on" if run["enabled"] else "off"}-{run["stepNs"]}'
 for name,digest in run['files'].items():assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest
 log=(folder/'ngspice.log').read_text();counts=re.findall(r'No\. of Data Rows\s*:\s*(\d+)',log);assert len(counts)==1;count=int(counts[0])
 maximum=0;at=None;edge=-1;first=True
 with (folder/'waveform.raw').open('rb') as f:
  names,declared=header(f);assert names==['time','v(clock)','v(out)'] and declared in (0,count)
  for t,clock,out in rows(f,3,count):
   if first:assert t==0;first=False
   while edge+1<len(edges) and edges[edge+1][0]<=t:edge+=1
   if edge<0:expected=0
   else:
    start,level=edges[edge];fraction=min(1.,max(0.,(t-start)/1e-9));expected=5*(fraction if level else 1-fraction)
   error=abs(out-expected)
   if error>maximum:maximum=error;at=t
  assert abs(t-.0011091)<=2*math.ulp(.0011091)
 if run['enabled']:assert run['maximumAdcTimeErrorSeconds']<=4*math.ulp(.0011091)
 results.append({'enabled':run['enabled'],'stepNs':run['stepNs'],'samples':count,'maximumAnalyticOutputErrorV':maximum,'timeSeconds':at})
result={'completed':True,'qualified':False,'scope':'Every sample against the analytic external-clock threshold plus 1-ns ADC and 10-ns bridge delays and 1-ns DAC ramp. Full board, nonlinear input crossing and rollback applicability remain open.','waveforms':results}
(root/'waveform-review.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
