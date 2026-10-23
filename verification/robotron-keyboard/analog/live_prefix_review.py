#!/usr/bin/env python3
"""Compare retained short live prefixes in absolute time, without qualification."""
import argparse,bisect,json,lzma
from pathlib import Path

def compare(paths):
 traces=[]
 for path in paths:
  rows=lzma.decompress(path.read_bytes()).decode().splitlines()
  traces.append((rows[0].split(),[list(map(float,r.split())) for r in rows[1:]]))
 if traces[0][0]!=traces[1][0]:raise ValueError('Different observed signals')
 a,b=traces[0][1],traces[1][1];times=[r[0] for r in b]
 if any(y<=x for x,y in zip(times,times[1:])):raise ValueError('Nonmonotonic time')
 if min(a[-1][0],b[-1][0])<.00102:raise ValueError('Incomplete short prefix')
 errors=[0.]*(len(a[0])-1)
 for row in a:
  if not .001005011<=row[0]<=min(a[-1][0],b[-1][0]):continue
  i=bisect.bisect_left(times,row[0]);lo,hi=b[max(0,i-1)],b[i]
  f=(row[0]-lo[0])/(hi[0]-lo[0]) if hi[0]!=lo[0] else 0
  for j in range(1,len(row)):errors[j-1]=max(errors[j-1],abs(row[j]-(lo[j]+f*(hi[j]-lo[j]))))
 return {'qualified':False,'endTimes':[a[-1][0],b[-1][0]],'comparison':'12.5 ns trace linearly interpolated at 25 ns trace sample times, after intervention; no phase alignment or tolerance qualification.','maximumAbsoluteDifferences':dict(zip(traces[0][0][1:],errors))}

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('traces',type=Path,nargs=2);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.write_text(json.dumps(compare(a.traces),indent=2)+'\n')
