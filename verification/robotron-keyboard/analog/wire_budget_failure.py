#!/usr/bin/env python3
"""Measure a deliberately incomplete capped wire log without claiming acceptance."""
import argparse,hashlib,json,lzma
from pathlib import Path


def inspect(root):
    receipt=json.loads((root/'run.json').read_text());reference=json.loads((root/'reference-assessment.json').read_text())
    if receipt.get('completed') or receipt.get('error')!='Logical log budget exceeded':raise ValueError('Expected capped incomplete run')
    p=root/'ngspice.log.xz.partial';digest=hashlib.sha256();size=0;tail=b'';last=None;boundaries=stable=0
    with lzma.open(p,'rb') as f:
        while True:
            data=f.read(4*1024**2)
            if not data:break
            size+=len(data)
            if size>4*1024**3:raise ValueError('Failed capture exceeded original cap')
            digest.update(data);data=tail+data;i=data.rfind(b'\n');tail=data[i+1:];data=data[:i+1]
            if len(tail)>1024**2:raise ValueError('Overlong partial record')
            boundaries+=data.count(b'VB_BRIDGE ');stable+=data.count(b'VB_STABLE equal=1\n')
            a=data.rfind(b'VB_BRIDGE ')
            if a>=0:last=data[a:data.find(b'\n',a)].decode('ascii')
    if size!=4*1024**3 or boundaries!=stable+1 or not stable or not last:raise ValueError('Unexpected capped log structure')
    expected=reference['observedState']['boundaries'];projection=size*expected/stable
    return dict(qualified=False,completed=False,failure='Logical log budget exceeded',logicalBytes=size,compressedBytes=p.stat().st_size,logicalSha256=digest.hexdigest(),completeStableBoundaries=stable,startedBoundaries=boundaries,lastBoundary=last,trailingBytes=len(tail),priorCompleteBoundaries=expected,constantBytesPerBoundaryProjection=projection,proposedLogicalLimitBytes=12*1024**3,unchangedCompressedLimitBytes=256*1024**2,unchangedTimeoutSeconds=3000,
        scope='Incomplete capture at the original logical byte cap, preserved as failure evidence. The boundary-count extrapolation informs a bounded retry; changing state can invalidate it. It proves neither full capture cost nor wire payload acceptance. The new limit does not alter HDL, circuit, window, native observers or acceptance checks.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.write_text(json.dumps(inspect(a.root),indent=2)+'\n')
