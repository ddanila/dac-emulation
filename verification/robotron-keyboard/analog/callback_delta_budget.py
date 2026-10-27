#!/usr/bin/env python3
"""Review exact real-bridge callback reconstruction and initial compact scan cost."""
import argparse,json
from pathlib import Path
import callback_board_budget as base
from callback_delta import block,image,reconstruct
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
DENSE_REVIEW=base.review


def review(root):
    result=DENSE_REVIEW(root)
    def frame(name):
        lines=(root/name).read_text().splitlines();f,end=block(lines)
        if end!=len(lines):raise ValueError('Extra compact budget records')
        return f
    reference=frame('callback-reference.txt')
    if reference['mode']!='R' or reference['tick']!=0:raise ValueError('Invalid board reference')
    dense=(root/'callbacks-before.txt').read_text().splitlines()
    if image(reference['tick'],reference['rows'])!=dense:raise ValueError('Reference differs from native board image')
    before=(root/'callback-delta-before.txt').read_bytes()
    if before!=(root/'callback-delta-after.txt').read_bytes():raise ValueError('Compact scan changed state')
    delta=frame('callback-delta-before.txt')
    if reconstruct(reference['rows'],delta)!=dense:raise ValueError('Compact board reconstruction differs')
    if delta['rows'] or delta['removed']:raise ValueError('Unexpected initial callback change')
    calls=result['initialStateProjection']['normalSnapshotCalls'];ref_size=(root/'callback-reference.txt').stat().st_size
    result['denseInitialLogicalBytes']=result['initialStateProjection']['logicalBytes']
    result['compactReferenceBytes']=ref_size;result['compactImageBytes']=len(before)
    result['compactScanTimings']=result.pop('scanTimings')
    # Tick zero has one digit; later captured ticks require extra digits.
    receipt=json.loads((root/'run.json').read_text());import re,math
    precision=re.findall(r'^:vpi_time_precision (-?\s*\d+);$',(root/'io.vvp').read_text(),re.M)
    if len(precision)!=1:raise ValueError('Missing compiled time precision')
    extra=max(0,len(str(math.ceil(receipt['projectionEndSeconds']/10**int(precision[0].replace(' ','')))))-1)
    result['initialStateProjection']=dict(normalSnapshotCalls=calls,compactLogicalBytes=ref_size+calls*(len(before)+extra),scanSeconds=calls*result['compactScanTimings']['meanSeconds'],excludesChangingStateCompressionAndOtherObservers=True)
    result['scope']='Actual initialized bridge callback bindings preserved while immutable-reference differences reconstruct every dense owner/list byte. Complete native admission scans and encoding are timed before first coroutine advance. Initial-state projection includes reference storage and later tick digit growth; it is not a changing-state bound.'
    result['notEstablished']=['Operational callback/association changes, combined capture and review cost','Deep typed VPI signal metadata and graph owner binding','Suspended traversal, shared result storage and general rollback']
    return result


def run(source,bridge,icarus,out):
    # Reuse the pinned diagnostic producer; add projection duration before the
    # compact review, without changing any running campaign source.
    def capture_review(root):
        p=root/'run.json';r=json.loads(p.read_text());r['projectionEndSeconds']=json.loads((source/'off/run.json').read_text())['endSeconds'];r['compactProducerSha256']=sha(Path(__file__));p.write_text(json.dumps(r,indent=2)+'\n')
        return review(root)
    old=base.review
    try:base.review=capture_review;base.run(source,bridge,icarus,out)
    finally:base.review=old


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('source','bridge','icarus','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed compact board assessment')
        print('Real-bridge compact callback budget verified.')
    else:
        if not all((a.source,a.bridge,a.icarus,a.out)):p.error('Need source, bridge, runtime and output')
        run(a.source,a.bridge,a.icarus,a.out)
