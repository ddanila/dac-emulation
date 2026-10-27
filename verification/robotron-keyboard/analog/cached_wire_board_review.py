#!/usr/bin/env python3
"""Qualify exact-input wire parsing reuse against the unchanged complete review."""
import argparse,copy,json,time
from pathlib import Path
import wire_board_review as original
import wire_board_budget_review as bounded
from cached_net_board_review import ExactBundleCache,sources
from reviewed_campaign_retention import files
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def canonical(value):
    return json.dumps(json.loads(json.dumps(value,allow_nan=False)),sort_keys=True,allow_nan=False)


def run(root,producer):
    root,producer=Path(root),Path(producer)
    bounded.budgets(root)
    pinned=sources();inputs=files(root);producer_sha=sha(producer)
    parser=original.bundle;cache=ExactBundleCache(parser);start=time.monotonic()
    try:
        original.bundle=cache
        assessment=bounded.assess(root,producer)
    finally:original.bundle=parser
    elapsed=time.monotonic()-start
    if sources()!=pinned or files(root)!=inputs or sha(producer)!=producer_sha:raise ValueError('Changed review sources, producer or captured evidence')
    return dict(completed=True,qualified=False,completeAssessmentExactlyEqual=False,
        elapsedSeconds=elapsed,cacheHits=cache.hits,cacheMisses=cache.misses,
        sources=pinned,producerSha256=producer_sha,inputFiles=inputs,
        assessment=json.loads(json.dumps(assessment,allow_nan=False)),
        scope='Candidate complete bounded wire review with one-entry exact-input bundle parsing reuse and isolated returned trees. All original semantic, waveform, firmware and budget checks execute. Equivalence to the independent original assessment is not yet established.')


def compare(candidate,root,producer,reference):
    if candidate.get('completed') is not True:raise ValueError('Incomplete cached candidate')
    if any(sha(HERE/name)!=digest for name,digest in candidate['sources'].items()):raise ValueError('Changed cached reviewer source')
    if files(Path(root))!=candidate['inputFiles'] or sha(Path(producer))!=candidate['producerSha256']:raise ValueError('Changed cached input evidence or producer')
    expected=json.loads(Path(reference).read_text())
    if canonical(candidate['assessment'])!=canonical(expected):raise ValueError('Cached complete review differs from original')
    result=copy.deepcopy(candidate);result['completeAssessmentExactlyEqual']=True;result['referenceSha256']=sha(Path(reference))
    result['scope']='Complete cached wire assessment equals the independent original assessment, including all faults, every normal waveform sample, firmware, state/lifetime and resource-budget checks. Captured files, producer and reviewer sources remain identical. Only exact-input bundle parsing is reused; returned trees are isolated. Timing is an observed cost, not a bound or broader rollback qualification.'
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('root','producer','out'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--reference',type=Path);a=p.parse_args()
    candidate=run(a.root,a.producer)
    # Preserve expensive work even if a supplied comparison later fails.
    a.out.with_suffix('.candidate.json').write_text(json.dumps(candidate,indent=2)+'\n')
    result=compare(candidate,a.root,a.producer,a.reference) if a.reference else candidate
    a.out.write_text(json.dumps(result,indent=2)+'\n')
