#!/usr/bin/env python3
"""Validate the disabled runtime control before assessing a forced Newton retry."""
import argparse
import json
import math
from pathlib import Path
import re
from bridge_rollback_log import analyze as bridge_analyze
from compare_firmware_io import sha
from filter_truncation_log import diagnostic
from network_refinement_review import events
from raw_pair_review import compare_raw
from retain_bridge_rollback import check as check_bridge
from rollback_audit_log import analyze as dispatch_analyze, REJECT
from trace_io import open_text


def log_data(directory, receipt):
    if receipt.get('error') or receipt['exitCode']!=0 or receipt['timedOut'] or receipt['solverDiagnostic']:
        raise ValueError('Incomplete retry capture')
    for name,digest in dict(receipt['inputs'],**{'io.cir':receipt['deckSha256']}).items():
        if sha(directory/name)!=digest:raise ValueError('Changed capture input')
    if sha(directory/'waveform.raw')!=receipt['storage']['waveform.raw']['sha256']:
        raise ValueError('Changed raw waveform')
    with open_text(directory/'ngspice.log') as stream:log=stream.read()
    if diagnostic(log) or 'SORRY:' in log:raise ValueError('Solver/HDL diagnostic')
    counts=re.findall(r'No\. of Data Rows\s*:\s*(\d+)',log)
    if len(counts)!=1:raise ValueError('Missing unique completion count')
    return log,int(counts[0])


def review(root, control, evidence):
    check_bridge(evidence)
    established=json.loads((evidence/'assessment.json').read_text())
    if sha(control/'run.json')!=sha(evidence/'run.json'):
        raise ValueError('Control differs from retained bridge evidence')
    prior=json.loads((control/'run.json').read_text())
    control_log,control_count=log_data(control,prior)
    with open_text(evidence/'ngspice.log') as stream:
        if control_log!=stream.read():raise ValueError('Changed complete control log')
    end=next(iter(established['comparisons'].values()))['lastSeconds']
    build=json.loads((root/'build.json').read_text())
    if build['parentRuntimeSha256']!=prior['runtime']['executable']['sha256']:
        raise ValueError('Different runtime ancestry')
    receipts=[];logs=[];counts=[]
    for mode in ('off','on'):
        directory=root/mode;r=json.loads((directory/'run.json').read_text())
        if r['mode']!=mode or r['buildSha256']!=sha(root/'build.json') or r['controlRunSha256']!=sha(control/'run.json'):
            raise ValueError('Changed retry provenance')
        expected_runtime=dict(prior['runtime'],executable=build['runtime'])
        if r['runtime']!=expected_runtime:raise ValueError('Different retry runtime or dependencies')
        expected_env=dict(prior['environment'])
        start=r.get('faultStartSeconds', .0010025)
        if isinstance(start, bool) or not isinstance(start, (int,float)) or not math.isfinite(start) or not 0<=start<end:
            raise ValueError('Retry start outside the complete capture')
        if receipts and r.get('faultStartSeconds')!=receipts[0].get('faultStartSeconds'):
            raise ValueError('Different requested retry times')
        if mode=='on':
            expected_env['ROBOTRON_FORCE_NEWTON_REJECT']='1'
            if 'faultStartSeconds' in r:
                expected_env['ROBOTRON_NEWTON_REJECT_START']=repr(float(start))
        if r['environment']!=expected_env:raise ValueError('Unexpected experimental environment')
        for key in ('externalDependencies','inputs','deckSha256'):
            if r[key]!=prior[key]:raise ValueError('Changed '+key)
        if sha(directory/'bridge.json')!=sha(control/'bridge.json'):
            raise ValueError('Changed bridge receipt')
        log,count=log_data(directory,r)
        receipts.append(r);logs.append(log);counts.append(count)
    def records(log):
        return [s.strip() for s in log.splitlines() if s.strip().startswith(('ROLLBACK_AUDIT ','TIME_AUDIT '))]
    if records(logs[0])!=records(control_log) or 'ROLLBACK_FAULT ' in logs[0]:
        raise ValueError('Disabled diagnostic changed solver/HDL history')
    exact=compare_raw(control/'waveform.raw',root/'off/waveform.raw',[control_count,counts[0]],end,exact=True)
    if events(logs[0])!=events(control_log):raise ValueError('Disabled diagnostic changed firmware')
    lines=logs[1].splitlines()
    faults=[(i,s.strip()) for i,s in enumerate(lines) if s.strip().startswith('ROLLBACK_FAULT ')]
    if len(faults)!=1:raise ValueError('Need exactly one injected retry')
    i,line=faults[0]
    match=re.fullmatch(r'ROLLBACK_FAULT kind=newton time=(\S+) original=0 injected=(\d+)',line)
    if not match or int(match[2])==0 or not start<=float.fromhex(match[1])<end:
        raise ValueError('Invalid injected retry record')
    following=next((s.strip() for s in lines[i+1:] if s.strip().startswith(('ROLLBACK_AUDIT ','TIME_AUDIT '))),None)
    reject=REJECT.fullmatch(following or '')
    if not reject or reject[1]!='newton' or float.fromhex(reject[2])!=float.fromhex(match[1]):
        raise ValueError('Fault did not immediately enter Newton retry')
    dispatch=dispatch_analyze(lines);timing=bridge_analyze(lines,expected_end=end)
    if dispatch['acceptedPoints']!=counts[1] or dispatch['firstAcceptedSeconds']!=0 or dispatch['lastAcceptedSeconds']!=end:
        raise ValueError('Incomplete injected audit')
    if dispatch['rejectedTrials'].get('newton')!=1:
        raise ValueError('Unexpected Newton rejection coverage')
    comparison=compare_raw(root/'off/waveform.raw',root/'on/waveform.raw',counts,end)
    firmware=events(logs[0])==events(logs[1]) and events(logs[1])['latchesMatch']
    ordering=(timing['timeOrderScreenPassed'] and dispatch['invalidTrialOrdering']==0
              and dispatch['unprotectedClientCalls']==0
              and not dispatch['trialsRejectedAfterClientCallbacks'].get('newton',0))
    return {'disabledControl':exact,'injectedAtSeconds':float.fromhex(match[1]),
            'comparison':comparison,'firmwareEventsMatch':firmware,'dispatch':dispatch,'timing':timing,
            'retryScreenPassed':firmware and ordering and comparison['maximumVoltageDifference']<=.01,
            'qualified':False,
            'boundary':'One forced Newton retry during the declared complete control window. Disabled runtime must reproduce every sample and solver/HDL record. Injection is not natural device nonconvergence, full-repeat coverage or general state rollback proof.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','control','evidence','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();a.out.write_text(json.dumps(review(a.root,a.control,a.evidence),indent=2)+'\n')
