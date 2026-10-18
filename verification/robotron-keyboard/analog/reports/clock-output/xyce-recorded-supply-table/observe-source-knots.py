"""Inspect where completed Xyce replay samples land relative to supply knots."""
from pathlib import Path
from array import array
import bisect,hashlib,json,math,sys
root=Path(sys.argv[1]);report=json.loads((root/'assessment.json').read_text())
assert report['completed'];duration=report['supply']['durationSeconds']
source_times=array('d')
with (root/'supply.txt').open() as f:
 for line in f:
  t=float(line.split()[0])
  if t<=duration:source_times.append(t)
result={'qualified':False,'assessmentSha256':hashlib.sha256((root/'assessment.json').read_bytes()).hexdigest(),'scriptSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'interpretation':'Observation of saved solver times only; matching a knot does not prove a particular internal scheduler event. No interpolation, timing acceptance or device qualification is changed.','runs':{}}
for label in ['coarse','fine']:
 times=array('d')
 with (root/label/'trace.txt').open() as f:
  next(f)
  for line in f:times.append(float(line.split()[0]))
 matched=0;worst={'differenceSeconds':0};examples=[]
 for t in source_times:
  i=bisect.bisect_left(times,t)
  candidates=times[max(0,i-1):min(len(times),i+1)]
  closest=min(candidates,key=lambda x:abs(x-t));difference=abs(closest-t)
  if difference<=4*max(math.ulp(t),math.ulp(closest)):matched+=1
  elif len(examples)<8:examples.append({'sourceSeconds':t,'nearestSavedSeconds':closest,'differenceSeconds':difference})
  if difference>worst['differenceSeconds']:worst={'sourceSeconds':t,'nearestSavedSeconds':closest,'differenceSeconds':difference}
 result['runs'][label]={'sourceKnots':len(source_times),'savedSamples':len(times),'knotsMatchedWithinFourUlps':matched,'maximumNearestDistance':worst,'firstUnmatched':examples}
(root/'source-knots.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result['runs'],indent=2))
