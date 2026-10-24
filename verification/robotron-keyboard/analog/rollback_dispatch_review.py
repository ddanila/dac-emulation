#!/usr/bin/env python3
"""Require complete unchanged waveforms before interpreting rollback audit calls."""
import argparse
import json
import math
from pathlib import Path
import re
from compare_firmware_io import sha
from filter_truncation_log import diagnostic
from live_raw_output import raw_deck
from live_raw_review import compare_trace, signal_name
from network_refinement_review import events
from raw_waveform import header
from raw_pair_review import compare_raw
from rollback_audit_log import analyze
from trace_io import open_binary, open_text

HERE=Path(__file__).resolve().parent


def review(root, baseline, build_receipt):
    original=json.loads((baseline/'run.json').read_text())
    if original['exitCode']!=0 or original['timedOut'] or original['solverDiagnostic'] or original['haltNs'] is not None:
        raise ValueError('Incomplete baseline')
    if json.loads((root/'baseline.json').read_text())!=original:
        raise ValueError('Different baseline receipt')
    deck=(baseline/'io.cir').read_text()
    if sha(baseline/'io.cir')!=original['deckSha256']:
        raise ValueError('Changed baseline circuit')
    raw = original.get('rawOutput', False)
    if raw:
        if len(re.findall(r'^run waveform\.raw$',deck,re.M))!=1 or re.search(r'^wrdata\b',deck,re.M):
            raise ValueError('Expected one direct raw writer')
        expected_deck,writers=deck,[]
        storage=original['compressedOutput']
        if storage.get('error') or sha(baseline/'waveform.raw')!=storage['streams']['waveform.raw']['sha256']:
            raise ValueError('Changed baseline waveform')
        with open_text(baseline/'ngspice.log') as stream:baseline_log=stream.read()
        if diagnostic(baseline_log) or 'SORRY:' in baseline_log:raise ValueError('Baseline diagnostic')
        count_matches=re.findall(r'No\. of Data Rows\s*:\s*(\d+)',baseline_log)
        if len(count_matches)!=1:raise ValueError('Missing baseline completion count')
        baseline_count=int(count_matches[0])
    else:
        expected_deck,writers=raw_deck(deck)
    saved=re.findall(r'^\.save (.+)$',deck,re.M)
    if len(saved)!=1 or set(saved[0].split())!=set(original['observationSignals']):
        raise ValueError('Incomplete baseline observation scope')
    if not raw:
        completion=json.loads((baseline/'completion-check.json').read_text())
        if completion.get('completed') is not True:
            raise ValueError('Baseline completion is unproven')
        for name,_ in writers:
            if sha(baseline/name)!=completion['traces'][name]['sha256']:
                raise ValueError('Changed baseline waveform')
    build=json.loads(build_receipt.read_text())
    receipts={};logs={};counts={};comparisons={}
    for mode in ('off','on'):
        directory=root/mode;r=json.loads((directory/'run.json').read_text());receipts[mode]=r
        if r.get('error') or r['exitCode']!=0 or r['timedOut'] or r['solverDiagnostic']:
            raise ValueError('Incomplete rollback control')
        if r['mode']!=mode or r['baselineRunSha256']!=sha(baseline/'run.json'):
            raise ValueError('Wrong control identity')
        if (directory/'io.cir').read_text()!=expected_deck or sha(directory/'io.cir')!=r['deckSha256']:
            raise ValueError('Changed circuit or sampling')
        if r['runtime']['executable']['sha256']!=build['runtimeSha256']:
            raise ValueError('Unrecognized audit runtime')
        for key in ('spinit','codeModels'):
            if r['runtime'][key]!=original['runtime'][key]:raise ValueError('Changed code models')
        if r['externalDependencies']!=original['externalDependencies'] or r['inputs']!=original['inputs']:
            raise ValueError('Changed live inputs or dependencies')
        for name,digest in r['inputs'].items():
            if sha(directory/name)!=digest:raise ValueError('Changed input file')
        if sha(directory/'waveform.raw')!=r['storage']['waveform.raw']['sha256']:
            raise ValueError('Changed raw output')
        with open_text(directory/'ngspice.log') as stream:logs[mode]=stream.read()
        if diagnostic(logs[mode]) or 'SORRY:' in logs[mode]:raise ValueError('Solver or HDL diagnostic')
        for token in ('DAC_ANCHORED enabled single-bit','MPFR_DIAGNOSTIC bits=256','CAP_ASSEMBLY mode=1','POSTCAP_ASSEMBLY mode=1'):
            if token not in logs[mode]:raise ValueError('Missing runtime acknowledgment')
        matches=re.findall(r'No\. of Data Rows\s*:\s*(\d+)',logs[mode])
        if len(matches)!=1:raise ValueError('Missing unique completion count')
        counts[mode]=int(matches[0])
        with open_binary(directory/'waveform.raw') as stream:names,declared=header(stream)
        if declared!=0 or set(map(signal_name,names))!={'time',*map(signal_name,original['observationSignals'])}:
            raise ValueError('Unexpected raw observation scope')
    for key in ('runtime','externalDependencies','inputs','deckSha256'):
        if receipts['off'][key]!=receipts['on'][key]:raise ValueError('Paired dependency changed')
    off=receipts['off']['environment'];on=receipts['on']['environment']
    if 'ROBOTRON_ROLLBACK_AUDIT' in off or on!={**off,'ROBOTRON_ROLLBACK_AUDIT':'1'}:
        raise ValueError('Audit is not the only environment difference')
    if 'ROLLBACK_AUDIT ' in logs['off']:raise ValueError('Disabled control emitted audit records')
    if counts['off']!=counts['on']:raise ValueError('Different complete row counts')
    for mode in ('off','on'):
        end=original['stopNs']*1e-9
        if raw:
            exact=compare_raw(baseline/'waveform.raw',root/mode/'waveform.raw',[baseline_count,counts[mode]],end,exact=True)
            comparisons[mode]={'waveform.raw':{'samples':exact['samples'],'firstSeconds':0.0,'lastSeconds':end}}
            continue
        comparisons[mode]={name:compare_trace(root/mode/'waveform.raw',baseline/name,counts[mode]) for name,_ in writers}
        for name,extent in comparisons[mode].items():
            end=original['stopNs']*1e-9
            if extent['samples']!=completion['traces'][name]['samples'] or extent['firstSeconds']!=0 or abs(extent['lastSeconds']-end)>2*math.ulp(end):
                raise ValueError('Incomplete waveform window')
    with open_text(baseline/'ngspice.log') as stream:reference_events=events(stream.read())
    if not reference_events['latchesMatch'] or any(events(log)!=reference_events for log in logs.values()):
        raise ValueError('Changed firmware events')
    audit=analyze(logs['on'].splitlines())
    if audit['acceptedPoints']!=counts['on'] or audit['firstAcceptedSeconds']!=0 or abs(audit['lastAcceptedSeconds']-end)>2*math.ulp(end):
        raise ValueError('Audit does not cover the complete waveform')
    return {'waveformsExactlyMatchBaseline':True,'firmwareEvents':reference_events,
            'comparisons':comparisons,'audit':audit,'qualified':False,
            'boundary':'Complete declared-window callback-order evidence only. Client callbacks do not prove internal HDL advancement or restoration; full-repeat and physical qualification remain separate.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','baseline','build-receipt','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();a.out.write_text(json.dumps(review(a.root,a.baseline,a.build_receipt),indent=2)+'\n')
