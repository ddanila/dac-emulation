"""Verify that the output-precision change leaves rounded simulated samples identical."""
from pathlib import Path
import itertools, lzma, hashlib, json, sys
BASE=Path('build/keyboard-controller-analog')
result={'qualified':False,'comparison':'Every full-precision token rounded to the previous eight decimal digits in scientific notation; headers compared by signal names. No sample interpolation or alignment.', 'traces':{}}
for label in sys.argv[1:] or ['coarse','fine']:
 for name in ['trace.txt','diagnostic-trace.txt']:
  old=BASE/'coupled-clock-tight-refinement'/label/(name+'.xz')
  new=BASE/'coupled-clock-full-precision'/label/(name+'.xz')
  count=0;first=None
  with lzma.open(old,'rt') as a,lzma.open(new,'rt') as b:
   assert next(a).split()==next(b).split()
   for left,right in itertools.zip_longest(a,b):
    count+=1
    if left is None or right is None:
     first={'row':count,'reason':'sample count differs'};break
    prior=left.split();current=[format(float(v),'.8e') for v in right.split()]
    if prior!=current:
     first={'row':count,'previous':prior,'newRounded':current};break
  result['traces'][label+'/'+name]={'samplesCompared':count,'identicalAtOriginalPrecision':first is None,'firstDifference':first,'originalCompressedSha256':hashlib.sha256(old.read_bytes()).hexdigest(),'newCompressedSha256':hashlib.sha256(new.read_bytes()).hexdigest()}
result['scriptSha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
out=BASE/'coupled-precision-comparison'/('-'.join(sys.argv[1:] or ['coarse','fine'])+'.json')
out.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
