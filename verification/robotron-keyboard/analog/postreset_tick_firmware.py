#!/usr/bin/env python3
"""Explain exact firmware-record changes without waiving baseline timing differences."""
import argparse,json
from pathlib import Path
from ttl7406_probe import sha


def review(root):
    full=json.loads((root/'assessment.json').read_text());records={n:(root/n/'firmware.log').read_text().splitlines() for n in ('off','coarse','fine','finest','retry')}
    if any(not lines for lines in records.values()):raise ValueError('Missing firmware records')
    if not all(records[n]==records['coarse'] for n in ('fine','finest','retry')):raise ValueError('Refined/retry firmware differs')
    if len(records['off'])!=len(records['coarse']):raise ValueError('Changed firmware record count')
    changes=[]
    for index,(old,new) in enumerate(zip(records['off'],records['coarse'])):
        if old==new:continue
        a,b=old.split(),new.split()
        if len(a)!=2 or len(b)!=2 or a[0]!='BUS_EDGE_PS' or b[0]!='BUS_EDGE_PS':raise ValueError('Non-timestamp firmware change')
        before,after=int(a[1]),int(b[1]);changes.append(dict(recordIndex=index,previousPs=before,exactTickPs=after,differencePs=after-before))
    expected={'disabled':True,'enabledEffect':not bool(changes),'coarseFine':True,'fineFinest':True,'forcedRetry':True}
    if full['firmwareRecordsExactlyEqual']!=expected:raise ValueError('Firmware summary disagrees with full review')
    return dict(qualified=False,fullAssessmentSha256=sha(root/'assessment.json'),firmwareFiles={n:sha(root/n/'firmware.log') for n in records},
                recordsPerRun=len(records['off']),changedBusEdgeTimestamps=changes,allOtherSelectedRecordsExactlyEqual=True,
                refinementAndRetryRecordsExactlyEqual=True,
                scope='Compare every retained selected firmware record. Changes are reported as absolute bus-edge timestamp differences, without alignment or automatic acceptance.',
                notEstablished=['Acceptance of changed baseline timing','Numerical convergence','Full log or waveform replay from selected firmware records'])

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path);p.add_argument('--check',action='store_true');a=p.parse_args();r=review(a.root)
    if a.check:
        if r!=json.loads((a.root/'firmware-comparison.json').read_text()):raise ValueError('Changed firmware comparison')
    else:
        if a.out is None:p.error('Need fresh output')
        with a.out.open('x') as f:json.dump(r,f,indent=2);f.write('\n')
