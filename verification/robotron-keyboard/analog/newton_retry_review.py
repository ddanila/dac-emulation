#!/usr/bin/env python3
"""Validate the disabled runtime control before assessing a forced Newton retry."""
import argparse
import json
import math
from pathlib import Path
import re
from bridge_rollback_log import analyze as bridge_analyze
from compare_firmware_io import sha
from audit_log import complete, equal, AUDIT, BUS
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
    path=directory/'ngspice.log'
    log_record=receipt['storage'].get('ngspice.log')
    if log_record is not None and sha(path)!=log_record['sha256']:
        raise ValueError('Changed captured audit log')
    return path,complete(path)


def review(root, control, evidence):
    check_bridge(evidence)
    established=json.loads((evidence/'assessment.json').read_text())
    if sha(control/'run.json')!=sha(evidence/'run.json'):
        raise ValueError('Control differs from retained bridge evidence')
    prior=json.loads((control/'run.json').read_text())
    control_log,control_info=log_data(control,prior)
    control_count=control_info['count']
    if not equal(control_log,evidence/'ngspice.log'):raise ValueError('Changed complete control log')
    end=next(iter(established['comparisons'].values()))['lastSeconds']
    build=json.loads((root/'build.json').read_text())
    if build['parentRuntimeSha256']!=prior['runtime']['executable']['sha256']:
        raise ValueError('Different runtime ancestry')
    receipts=[];logs=[];counts=[];infos=[]
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
        log,info=log_data(directory,r)
        receipts.append(r);logs.append(log);counts.append(info['count']);infos.append(info)
    if not equal(logs[0],control_log,AUDIT) or infos[0]['faults']:
        raise ValueError('Disabled diagnostic changed solver/HDL history')
    exact=compare_raw(control/'waveform.raw',root/'off/waveform.raw',[control_count,counts[0]],end,exact=True)
    if not equal(logs[0],control_log,BUS):raise ValueError('Disabled diagnostic changed firmware')
    faults=infos[1]['faults']
    if len(faults)!=1:raise ValueError('Need exactly one injected retry')
    match=re.fullmatch(r'ROLLBACK_FAULT kind=newton time=(\S+) original=0 injected=(\d+)',faults[0]['record'])
    if not match or int(match[2])==0 or not start<=float.fromhex(match[1])<end:
        raise ValueError('Invalid injected retry record')
    following=faults[0]['following']
    reject=REJECT.fullmatch(following or '')
    if not reject or reject[1]!='newton' or float.fromhex(reject[2])!=float.fromhex(match[1]):
        raise ValueError('Fault did not immediately enter Newton retry')
    with open_text(logs[1]) as stream:dispatch=dispatch_analyze(stream)
    with open_text(logs[1]) as stream:timing=bridge_analyze(stream,expected_end=end)
    if dispatch['acceptedPoints']!=counts[1] or dispatch['firstAcceptedSeconds']!=0 or dispatch['lastAcceptedSeconds']!=end:
        raise ValueError('Incomplete injected audit')
    if dispatch['rejectedTrials'].get('newton')!=1:
        raise ValueError('Unexpected Newton rejection coverage')
    comparison=compare_raw(root/'off/waveform.raw',root/'on/waveform.raw',counts,end)
    firmware=equal(logs[0],logs[1],BUS) and infos[1]['latchesMatch']
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
