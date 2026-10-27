#!/usr/bin/env python3
"""Replay all initialized keyboard compact records and report measured costs."""
import argparse,json,math
from pathlib import Path
import scope_metadata_board_budget as previous
from scope_metadata_compact import Decoder


def review(root):
    prior=previous.review(root);results={};timings={k:[] for k in ('metadata','references')}
    for line in (root/'metadata-compact-budget.txt').read_text().splitlines():
        a=line.split()
        if len(a)!=4 or a[0]!='COMPACT_SCAN' or a[1] not in timings or int(a[2])!=len(timings[a[1]]):raise ValueError('Invalid compact timing order')
        value=float(a[3])
        if not math.isfinite(value) or value<=0:raise ValueError('Invalid compact cost')
        timings[a[1]].append(value)
    calls=prior['initialStateProjection']['normalSnapshotCalls']
    for key,stem,reference in (('metadata','metadata',False),('references','metadata-references',True)):
        dense=(root/(stem+'-before.txt')).read_text()
        if dense!=(root/(stem+'-compact-after.txt')).read_text():raise ValueError('Compact observation changed native image')
        decoder=Decoder(reference);lines=(root/(stem+'-compact.txt')).read_text().splitlines();i=0;records=[]
        while i<len(lines):
            start=i
            while i<len(lines) and lines[i]!=decoder.tag+'_END':i+=1
            if i==len(lines):raise ValueError('Truncated compact board record')
            i+=1;record=lines[start:i]
            if decoder.decode(record)!=dense:raise ValueError('Board dense reconstruction differs')
            records.append(len(('\n'.join(record)+'\n').encode()))
        if decoder.sequence!=64 or decoder.full!=1 or decoder.reused!=63 or len(timings[key])!=64:raise ValueError('Incomplete board compact controls')
        body_bytes=len(decoder.body.encode());values=timings[key]
        # Sequence width is included; arbitrary future ticks get their full u64 width.
        unchanged_bytes=records[0]+sum(len(f'{decoder.tag}_BEGIN 1 {2**64-1} {n} 0 {body_bytes}\n{decoder.tag}_END\n') for n in range(2,calls+1))
        results[key]=dict(records=64,fullImages=1,reusedImages=63,denseBytes=64*len(dense.encode()),
            compactBytes=sum(records),firstRecordBytes=records[0],lastRecordBytes=records[-1],cachedBodyBytes=body_bytes,
            firstScanSeconds=values[0],repeatMeanSeconds=sum(values[1:])/63,minSeconds=min(values),maxSeconds=max(values),
            unchangedBodyProjection=dict(snapshotCalls=calls,logicalBytesWithMaximumTickWidth=unchanged_bytes,
                scanSeconds=values[0]+(calls-1)*sum(values[1:])/63))
    return dict(qualified=False,controlsPassed=True,allDenseImagesExactlyReconstructed=True,initializedBoard=prior,
        compactMeasurements=results,cachedBodyContentBytes=sum(v['cachedBodyBytes'] for v in results.values()),
        scope='All 64 metadata and 64 reference records from the initialized actual keyboard reconstruct dense bytes exactly. Complete native scans remain enabled and dense post-scan images are unchanged. Timings include serialization and file flush. Cached content byte counts exclude allocator capacity, transient buffers and peak RSS. Future projections assume unchanged bodies; changed-state output, combined operational cost and lifecycle remain unqualified.')


def run(source,bridge,icarus,out):
    previous.run(source,bridge,icarus,out)
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','bridge','icarus','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.source,a.bridge,a.icarus,a.out)
