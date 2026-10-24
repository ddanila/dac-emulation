#!/usr/bin/env python3
"""Require complete sample and scheduling equality for the live cache control."""
import argparse
import json
from pathlib import Path
from bridge_rollback_log import analyze
from compare_firmware_io import sha
from network_refinement_review import events
from newton_retry_review import log_data
from raw_pair_review import compare_raw
from retain_bridge_rollback import check as check_bridge
from trace_io import open_text
from ttl7406_probe import sha as file_sha


def check(out):
    expected=json.loads((out/'manifest.json').read_text())
    actual={str(p.relative_to(out)):file_sha(p) for p in out.rglob('*') if p.is_file() and p.name!='manifest.json'}
    if actual!=expected:raise ValueError('Changed retained cache evidence')
    result=json.loads((out/'assessment.json').read_text())
    with open_text(out/'ngspice.log') as stream:
        timing=analyze(stream,expected_end=result['completeWaveformComparison']['endSeconds'])
    if timing!=result['timing']:raise ValueError('Changed retained cache timing interpretation')


def review(capture,control,evidence):
    check_bridge(evidence)
    if sha(control/'run.json')!=sha(evidence/'run.json'):
        raise ValueError('Changed established control')
    prior=json.loads((control/'run.json').read_text())
    current=json.loads((capture/'run.json').read_text())
    established=json.loads((evidence/'assessment.json').read_text())
    if prior['environment'].get('ROBOTRON_EVAL_CACHE')!='off':
        raise ValueError('Need an uncached control')
    expected=dict(prior['environment'],ROBOTRON_EVAL_CACHE='exact')
    if current['environment']!=expected:raise ValueError('Changed environment beyond cache mode')
    if current['controlRunSha256']!=sha(control/'run.json'):
        raise ValueError('Changed cache-control ancestry')
    if current['generatorSha256']!=sha(capture/'capture-generator.py'):
        raise ValueError('Changed cache producer')
    for key in ('runtime','externalDependencies','inputs','deckSha256'):
        if current[key]!=prior[key]:raise ValueError('Changed '+key)
    if sha(capture/'bridge.json')!=sha(control/'bridge.json'):
        raise ValueError('Changed bridge identity')
    control_log,n=log_data(control,prior);log,m=log_data(capture,current)
    with open_text(evidence/'ngspice.log') as stream:
        if control_log!=stream.read():raise ValueError('Changed established log')
    def records(text):
        return [line.strip() for line in text.splitlines() if line.strip().startswith(('ROLLBACK_AUDIT ','TIME_AUDIT '))]
    if records(log)!=records(control_log) or 'ROLLBACK_FAULT ' in log:
        raise ValueError('Cache changed solver/HDL history')
    if events(log)!=events(control_log):raise ValueError('Cache changed firmware events')
    end=next(iter(established['comparisons'].values()))['lastSeconds']
    waveform=compare_raw(control/'waveform.raw',capture/'waveform.raw',[n,m],end,exact=True)
    timing=analyze(log.splitlines(),expected_end=end)
    if timing!=established['timing']:raise ValueError('Changed bridge timing interpretation')
    return {'completeWaveformComparison':waveform,'solverAndHdlHistoryExactlyEqual':True,
            'firmwareEventsExactlyEqual':True,'timing':timing,'qualified':False,
            'boundary':'Complete bounded reset-release cache equivalence only. One enabled run is not a repeatable performance measurement or full-service qualification. Keep caching opt-in.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('capture','control','evidence'):p.add_argument('--'+name,type=Path)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--check',action='store_true')
    a=p.parse_args()
    if a.check:check(a.out)
    else:
        if not all((a.capture,a.control,a.evidence)):p.error('Review requires complete capture and established control')
        a.out.write_text(json.dumps(review(a.capture,a.control,a.evidence),indent=2)+'\n')
