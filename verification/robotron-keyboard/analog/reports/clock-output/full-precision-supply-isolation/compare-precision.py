"""Run from core root after both recorded-supply experiments complete."""
import sys, json, hashlib, bisect
from pathlib import Path
from array import array
sys.path.insert(0,'verification/robotron-keyboard/analog')
from clock_convergence import compare_clocks
BASE=Path('build/keyboard-controller-analog')
LEFT=BASE/'clock-filesource-replay-explicit-scale'
RIGHT=BASE/'clock-full-precision-supply-replay'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def supply(p):
 t,v=array('d'),array('d')
 with p.open() as f:
  for line in f:
   x,y=map(float,line.split());t.append(x);v.append(y)
 return t,v
lt,lv=supply(LEFT/'supply.txt');rt,rv=supply(RIGHT/'supply.txt')
# Exact maxima for the two piecewise-linear curves occur at their union of knots.
i=j=0;maximum={'volts':0};startup={'volts':0};end=250e-6
while i<len(lt)-1 and j<len(rt)-1:
 t=min(lt[i+1],rt[j+1],end)
 a=lv[i]+(lv[i+1]-lv[i])*(t-lt[i])/(lt[i+1]-lt[i])
 b=rv[j]+(rv[j+1]-rv[j])*(t-rt[j])/(rt[j+1]-rt[j])
 difference=abs(a-b)
 event={'volts':difference,'timeSeconds':t,'coarseSupplyVolts':a,'fineSupplyVolts':b}
 if difference>maximum['volts']:maximum=event
 if 99e-6<=t<=104e-6 and difference>startup['volts']:startup=event
 if t==end:break
 if lt[i+1]<=t:i+=1
 if rt[j+1]<=t:j+=1
# Include the bounded window endpoints as well as all its internal knots.
for t in (99e-6,104e-6):
 i=bisect.bisect_right(lt,t)-1;j=bisect.bisect_right(rt,t)-1
 a=lv[i]+(lv[i+1]-lv[i])*(t-lt[i])/(lt[i+1]-lt[i])
 b=rv[j]+(rv[j+1]-rv[j])*(t-rt[j])/(rt[j+1]-rt[j])
 if abs(a-b)>startup['volts']:startup={'volts':abs(a-b),'timeSeconds':t,'coarseSupplyVolts':a,'fineSupplyVolts':b}
reports=[json.loads((p/'assessment.json').read_text()) for p in (LEFT,RIGHT)]
assert all(r['completed'] for r in reports)
for key in ('runtime','connectivitySha256','scriptSha256','helpers'):assert reports[0][key]==reports[1][key],key
result={'qualified':False,'scriptSha256':sha(Path(__file__)),'inputAssessments':[{'path':str(p/'assessment.json'),'sha256':sha(p/'assessment.json')} for p in (LEFT,RIGHT)], 'supplyDifference':{'maximum':maximum,'startupWindowMaximum':startup,'scopeSeconds':[0,end]},'sameStepClockComparisons':{}}
for label,step in [('coarse',.25),('fine',.125)]:
 result['sameStepClockComparisons'][label]=compare_clocks(LEFT/label/'trace.txt',RIGHT/label/'trace.txt',step,step,columns=3)
result['boundary']='Changes the precision of the same prescribed coupled supply recording at each fixed timestep; the coupled coarse rerun matches every original sample after rounding. Supply voltages retain original printed rounding; source breakpoint scheduling differs from the coupled board. A cross-supply difference is a sensitivity observation, not a timestep qualification.'
(BASE/'supply-replay-comparison/precision-assessment.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'supplyDifference':result['supplyDifference'],'clocks':{k:{x:v[x] for x in ['passed','maximumBracketDifferenceNs','firstDifference']} for k,v in result['sameStepClockComparisons'].items()}},indent=2))
