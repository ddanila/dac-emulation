#!/usr/bin/env python3
"""Recompute retained keyboard comparison and measured resource accounting."""
import argparse
import json
import math
from pathlib import Path
from retained_stream_review import replay
from ttl7406_probe import sha

HERE=Path(__file__).resolve().parent


def assess(root,baseline):
    report=json.loads((root/'assessment.json').read_text())
    capture=json.loads((root/'capture/assessment.json').read_text())
    prior=json.loads((baseline/'capture/assessment.json').read_text())
    if report['sourceReceiptSha256']!=sha(baseline/'capture/assessment.json'):
        raise ValueError('Changed original comparison receipt')
    if report['benchmarkSha256']!=sha(HERE/'keyboard_retained_benchmark.py'):
        raise ValueError('Changed benchmark producer')
    for name,digest in capture['sources'].items():
        if sha(HERE/name)!=digest:raise ValueError('Changed capture source')
    if capture['runtime']!=prior['runtime'] or capture['externalDependencies']!=prior['externalDependencies'] or capture['environment']!=prior['environment']:
        raise ValueError('Changed runtime, dependencies or environment')
    if capture['stepsNs']!=prior['stepsNs'] or capture['endNs']!=prior['endNs']:
        raise ValueError('Changed observation window/refinements')
    if capture['inputs']!=prior['inputs']:raise ValueError('Changed firmware/HDL inputs')
    for i in range(3):
        if (root/f'inputs-{i}/io.cir').read_text()!=(baseline/f'inputs-{i}/io.cir').read_text():
            raise ValueError('Changed source circuit')
        for name,digest in capture['inputs'].items():
            if sha(root/f'inputs-{i}'/name)!=digest:raise ValueError('Changed retained input')
    reviewed=replay(root/'capture')
    if reviewed['comparisons']!=prior['transport']['comparisons'] or reviewed['comparisons']!=capture['transport']['comparisons']:
        raise ValueError('Changed numerical comparison')
    before,after=[row['signals'] for row in reviewed['comparisons']]
    failures={name:{'previous':before[name]['maximumAbsoluteDifference'],'finest':v['maximumAbsoluteDifference']}
              for name,v in after.items() if v['unit']=='V' and (v['maximumAbsoluteDifference']>.01 or v['maximumAbsoluteDifference']>before[name]['maximumAbsoluteDifference'])}
    if capture['voltageFailures']!=failures or any(r['voltageGatePassed']!=(not failures) for r in (report,capture,prior)):
        raise ValueError('Changed voltage gate')
    resource=json.loads((root/'resource-samples.json').read_text());samples=resource['samples']
    if resource['errors'] or len(samples)<2:raise ValueError('Missing resource observations')
    stamps=[s['seconds'] for s in samples]
    if any(not math.isfinite(t) or t<0 for t in stamps) or any(a>=b for a,b in zip(stamps,stamps[1:])):
        raise ValueError('Invalid resource observation times')
    if any(type(s['rssKiB']) is not int or s['rssKiB']<=0 or type(s['processes']) is not int or s['processes']<=0 for s in samples):
        raise ValueError('Invalid resource observation')
    if report['sampledMaximumTreeRssKiB']!=max(s['rssKiB'] for s in samples):raise ValueError('Changed sampled RSS peak')
    if not math.isfinite(report['elapsedSeconds']) or report['elapsedSeconds']<stamps[-1]:raise ValueError('Invalid duration')
    usage=reviewed['storageUsage']
    if report['storageUsage']!=usage or report['compressedLogBytes']!=usage['compressedLogBytes'] or report['rawBytesCompared']!=usage['logicalRawBytes']:
        raise ValueError('Changed storage accounting')
    if report['storageLimits']!=capture['transport']['storageLimits']:raise ValueError('Changed storage caps')
    if any(r['qualified'] is not False for r in (report,capture,prior)):raise ValueError('Unexpected qualification claim')
    return dict(reviewCompleted=True,qualified=False,baselineComparisonsExactlyEqual=True,
        replayExactlyPreserved=True,voltageGatePassed=not failures,voltageFailures=failures,
        elapsedSeconds=report['elapsedSeconds'],sampledMaximumTreeRssKiB=report['sampledMaximumTreeRssKiB'],
        resourceSampleCount=len(samples),firstResourceSampleSeconds=stamps[0],lastResourceSampleSeconds=stamps[-1],
        maximumResourceSamplingGapSeconds=max(b-a for a,b in zip(stamps,stamps[1:])),storageUsage=usage,
        scope='Complete bounded 20-us keyboard transport and waveform replay. RSS covers capture sampling only, excludes later replay and is not an exact peak. Runtime includes replay. No extrapolation to full-repeat budgets.',
        receipts={name:sha(root/name) for name in ('assessment.json','capture/assessment.json','resource-samples.json')},
        reviewerSha256=sha(Path(__file__)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('root','baseline','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();result=assess(a.root,a.baseline)
    with a.out.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
