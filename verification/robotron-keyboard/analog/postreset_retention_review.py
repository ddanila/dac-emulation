#!/usr/bin/env python3
"""Audit full-window retention budgets; optionally repeat every sample comparison."""
import argparse
import hashlib
import json
import lzma
import math
from pathlib import Path
from retained_stream_review import replay
from ttl7406_probe import sha

HERE=Path(__file__).resolve().parent


def verify_archive(path, expected):
    """Bind archived contents to the capture receipt without parsing samples."""
    digest=hashlib.sha256();size=0
    with lzma.open(path,'rb') as stream:
        while True:
            data=stream.read(min(65536,expected['bytes']-size+1))
            if not data:break
            size+=len(data)
            if size>expected['bytes']:raise ValueError('Archive exceeds declared size')
            digest.update(data)
    if size!=expected['bytes'] or digest.hexdigest()!=expected['sha256']:
        raise ValueError('Changed archived contents')


def assess(root,full=False):
    report=json.loads((root/'assessment.json').read_text())
    preflight=json.loads((root/'preflight.json').read_text())
    transport=json.loads((root/'capture/transport.json').read_text())
    prior=json.loads((root/'baseline-assessment.json').read_text())
    resources=json.loads((root/'resource-samples.json').read_text())
    if not report['completed'] or report['qualified'] or not transport['completed'] or transport['qualified']:
        raise ValueError('Invalid qualification status')
    if report['sources']!=preflight['sources']:raise ValueError('Changed source binding')
    for n,h in preflight['sources'].items():
        if sha(HERE/n)!=h:raise ValueError('Changed source '+n)
    if report['inputReceipts']!=preflight['inputReceipts']:raise ValueError('Changed inputs')
    usage={k:0 for k in transport['storageUsage']}
    source_compressed={}
    for i,name in enumerate(('coarse','fine','finest')):
        path=root/(name+'-run.json');original=json.loads(path.read_text())
        if sha(path)!=report['inputReceipts'][name] or sha(path)!=prior['receipts'][name]:
            raise ValueError('Changed producer receipt')
        raw=original['storage']['waveform.raw']
        if any(transport['streams'][i][k]!=raw[k] or transport['rawArchives'][i][k]!=raw[k] for k in ('sha256','bytes')):
            raise ValueError('Changed complete raw identity')
        if transport['streams'][i]['endSeconds']!=.00116 or transport['streams'][i]['samples']!=original['logSummary']['count']:
            raise ValueError('Changed complete window/count')
        if any(transport['logs'][i][k]!=original['log'][k] for k in ('sha256','bytes')):
            raise ValueError('Changed authentic source log')
        usage['logicalRawBytes']+=raw['bytes'];usage['logicalLogBytes']+=original['log']['bytes']
        for suffix,key in (('raw','compressedRawBytes'),('log','compressedLogBytes')):
            p=root/f'capture/{i}.{suffix}.xz'
            verify_archive(p,raw if suffix=='raw' else original['log'])
            if suffix=='raw' and p.stat().st_size!=transport['rawArchives'][i]['compressedBytes']:
                raise ValueError('Changed compressed raw size')
            usage[key]+=p.stat().st_size
            source_compressed[str(p.relative_to(root))]={'bytes':p.stat().st_size,'sha256':sha(p)}
    mapping={'logicalRawBytes':'max_raw_bytes','compressedRawBytes':'max_compressed_raw_bytes',
             'logicalLogBytes':'max_log_bytes','compressedLogBytes':'max_compressed_log_bytes','logLineBytes':'max_log_line_bytes'}
    if transport['storageLimits']!={k:preflight['limits'][v] for k,v in mapping.items()}:
        raise ValueError('Changed configured budget')
    if usage!=transport['storageUsage'] or usage!=report['storageUsage'] or any(v>transport['storageLimits'][k] for k,v in usage.items()):
        raise ValueError('Invalid storage budget/accounting')
    expected=[prior['comparisons'][k] for k in ('coarseFine','fineFinest')]
    if transport['comparisons']!=expected or report['originalVoltageGate']!=prior['voltageGate']:
        raise ValueError('Changed comparison or gate')
    if full and replay(root/'capture')['comparisons']!=expected:raise ValueError('Changed full replay')
    samples=resources['samples']
    if resources['errors'] or len(samples)<2 or len(samples)!=report['sampleCount']:raise ValueError('Invalid resource history')
    times=[s['seconds'] for s in samples]
    if any(not math.isfinite(t) or t<0 for t in times) or any(b<=a for a,b in zip(times,times[1:])):
        raise ValueError('Invalid observation ordering')
    if report['sampledMaximumTreeRssKiB']!=max(s['rssKiB'] for s in samples):raise ValueError('Changed sampled peak')
    return dict(reviewCompleted=True,qualified=False,everySampleReplayedInThisReview=full,
        originalNumericalGatePassed=prior['voltageGate']['passed'],storageUsage=usage,
        captureReplaySeconds=report['captureReplaySeconds'],archiveReviewSeconds=report['archiveReviewSeconds'],
        sampledMaximumTreeRssKiB=report['sampledMaximumTreeRssKiB'],maximumSampleGapSeconds=max(b-a for a,b in zip(times,times[1:])),
        compressedArtifacts=source_compressed,receipts={n:sha(root/n) for n in ('assessment.json','preflight.json','resource-samples.json','capture/transport.json')},
        reviewerSha256=sha(Path(__file__)),
        scope='Complete 1.16-ms archived exact-tick refinements. Resource sampling excludes preflight hashing, includes retention and subsequent replay, and cannot establish an exact peak. No new simulation, full repeat or numerical admission. Every archive is decompressed and matched to its logical receipt. --full additionally repeats every waveform comparison; otherwise sample comparisons are not rerun. Compressed hashes identify the reviewed archives.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--full',action='store_true');a=p.parse_args()
    result=assess(a.root,a.full)
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
