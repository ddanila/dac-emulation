#!/usr/bin/env python3
"""Validate the isolated bridge logger before interpreting live HDL time records."""
import argparse
import json
import math
from pathlib import Path
import re
from bridge_rollback_log import analyze
from compare_firmware_io import sha
from filter_truncation_log import diagnostic
from live_bridge_time_capture import substitute_vpi
from live_raw_review import compare_trace
from network_refinement_review import events
from rollback_dispatch_review import review as dispatch_review
from trace_io import open_text


def review(capture, control, baseline, base_bridge, build):
    established=dispatch_review(control.parent,baseline,build)
    original=json.loads((baseline/'run.json').read_text())
    prior=json.loads((control/'run.json').read_text())
    current=json.loads((capture/'run.json').read_text())
    base=json.loads(base_bridge.read_text());audit=json.loads((capture/'bridge.json').read_text())
    if current.get('error') or current['exitCode']!=0 or current['timedOut'] or current['solverDiagnostic']:
        raise ValueError('Incomplete bridge timing capture')
    if current['controlRunSha256']!=sha(control/'run.json') or current['baseBridgeReceiptSha256']!=sha(base_bridge):
        raise ValueError('Changed control identity')
    if current['bridgeReceiptSha256']!=sha(capture/'bridge.json') or audit['audit']['baseBridgeSha256']!=sha(base_bridge):
        raise ValueError('Changed bridge provenance')
    end=original['stopNs']*1e-9
    start,stop=audit['audit']['windowSeconds']
    if start!=0 or stop<=end:raise ValueError('Logger does not cover transient window')
    for key in ('runtime','environment','inputs'):
        if current[key]!=prior[key]:raise ValueError('Changed '+key)
    for name,lib in audit['libraries'].items():
        if name!='vpi' and lib!=base['libraries'][name]:raise ValueError('Changed non-VPI library')
    expected=[audit['libraries']['vpi'] if d==base['libraries']['vpi'] else d for d in prior['externalDependencies']]
    if sorted(expected,key=lambda d:d['path'])!=sorted(current['externalDependencies'],key=lambda d:d['path']):
        raise ValueError('Unintended dependency change')
    expected_deck=substitute_vpi((control/'io.cir').read_text(),base['libraries']['vpi']['path'],audit['libraries']['vpi']['path'])
    if (capture/'io.cir').read_text()!=expected_deck or sha(capture/'io.cir')!=current['deckSha256']:
        raise ValueError('Changed circuit beyond VPI path')
    for name,digest in current['inputs'].items():
        if sha(capture/name)!=digest:raise ValueError('Changed firmware input')
    if sha(capture/'waveform.raw')!=current['storage']['waveform.raw']['sha256']:
        raise ValueError('Changed raw waveform')
    with open_text(capture/'ngspice.log') as stream:log=stream.read()
    if diagnostic(log) or 'SORRY:' in log:raise ValueError('Solver/HDL diagnostic')
    with open_text(control/'ngspice.log') as stream:control_log=stream.read()
    def dispatch_records(text):return [line.strip() for line in text.splitlines() if line.strip().startswith('ROLLBACK_AUDIT ')]
    if dispatch_records(log)!=dispatch_records(control_log):raise ValueError('Logging changed solver dispatch history')
    counts=re.findall(r'No\. of Data Rows\s*:\s*(\d+)',log)
    if len(counts)!=1:raise ValueError('Missing unique completion count')
    count=int(counts[0])
    comparisons={name:compare_trace(capture/'waveform.raw',baseline/name,count) for name in established['comparisons']['on']}
    for name,value in comparisons.items():
        if value!=established['comparisons']['on'][name]:raise ValueError('Changed complete waveform extent')
        if abs(value['lastSeconds']-end)>2*math.ulp(end):raise ValueError('Incomplete window')
    if events(log)!=established['firmwareEvents']:raise ValueError('Changed firmware events')
    timing=analyze(log.splitlines())
    if timing['completedClientCallbacks']!=sum(established['audit']['clientCalls'].values()):
        raise ValueError('Missing client callback coverage')
    return {'waveformsExactlyMatchBaseline':True,'dispatchRecordsExactlyMatchControl':True,
            'firmwareEvents':established['firmwareEvents'],'comparisons':comparisons,'timing':timing,
            'qualified':False,'boundary':'Complete bounded reset-release logging comparison. Observed HDL timing does not establish general state rollback, unexercised Newton rejection, or full-repeat qualification.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('capture','control','baseline','base-bridge','build','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();a.out.write_text(json.dumps(review(a.capture,a.control,a.baseline,a.base_bridge,a.build),indent=2)+'\n')
