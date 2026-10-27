#!/usr/bin/env python3
"""Independently qualify exact-input caching for the pinned net-board reviewer."""
import argparse
import copy
import json
from pathlib import Path
import sys
import time
import net_board_review as original
from ttl7406_probe import sha

HERE=Path(__file__).resolve().parent


class ExactBundleCache:
    """One-entry cache of a pure parser; callers receive isolated result trees."""
    def __init__(self,parser):
        self.parser=parser;self.key=None;self.value=None;self.hits=0;self.misses=0
    def __call__(self,lines,identities):
        key=(tuple(lines),json.dumps(identities,sort_keys=True,allow_nan=False))
        if key!=self.key:
            # A failed parse must never populate the cache.
            value=self.parser(lines,identities)
            self.value=value;self.key=key;self.misses+=1
        else:self.hits+=1
        return copy.deepcopy(self.value)


def sources():
    paths={Path(__file__).resolve()}
    for module in tuple(sys.modules.values()):
        name=getattr(module,'__file__',None)
        if name:
            path=Path(name).resolve()
            if path.parent==HERE and path.suffix=='.py':paths.add(path)
    return {p.name:sha(p) for p in sorted(paths)}


def run(root,producer,reference,diagnostic=None):
    pinned=sources();parser=original.bundle;cache=ExactBundleCache(parser)
    start=time.monotonic()
    try:
        original.bundle=cache
        assessment=original.assess(root,producer)
    finally:original.bundle=parser
    elapsed=time.monotonic()-start
    if sources()!=pinned:raise ValueError('Changed reviewer source')
    expected=json.loads(reference.read_text())
    # The retained assessment is JSON: native integer dictionary keys become
    # strings on disk. Compare canonical serialized values, including scalar types.
    normalized=json.loads(json.dumps(assessment,allow_nan=False))
    exact=json.dumps(normalized,sort_keys=True,allow_nan=False)==json.dumps(expected,sort_keys=True,allow_nan=False)
    if not exact:
        if diagnostic is not None:
            diagnostic.write_text(json.dumps(dict(completed=False,qualified=False,
                completeAssessmentExactlyEqual=False,elapsedSeconds=elapsed,
                cacheHits=cache.hits,cacheMisses=cache.misses,sources=pinned,
                referenceSha256=sha(reference),assessment=normalized),indent=2)+'\n')
        raise ValueError('Cached review differs from original complete review')
    return dict(completed=True,qualified=False,completeAssessmentExactlyEqual=True,
        elapsedSeconds=elapsed,cacheHits=cache.hits,cacheMisses=cache.misses,
        sources=pinned,referenceSha256=sha(reference),assessment=assessment,
        scope='Complete original net-board acceptance including all controls, every raw sample comparison, firmware and state lifetime checks. Only pure bundle parsing is cached for exactly identical record sequences and module identities. Cached results are deep-copied. One-entry cache; original reviewer and capture sources unchanged. Elapsed time is an observation, not a runtime bound or general rollback qualification.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','producer','reference','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();result=run(a.root,a.producer,a.reference,a.out.with_suffix('.mismatch.json'))
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({k:result[k] for k in ('completed','completeAssessmentExactlyEqual','elapsedSeconds','cacheHits','cacheMisses')},indent=2))
