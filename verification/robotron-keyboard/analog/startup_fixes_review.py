#!/usr/bin/env python3
"""Review bounded interactions without claiming full startup qualification."""
import argparse
import json
from pathlib import Path
from audit_log import equal
from compare_firmware_io import sha as logical_sha
from raw_pair_review import compare_raw
from staged_output_review import runtime_summary, check
from startup_fixes_capture import VARIANTS
from trace_io import open_text
from ttl7406_probe import sha


def validate_receipt(receipt,baseline,mode,build_digest,runtime):
    if receipt['exitCode']!=0 or receipt['inputs']!=baseline['inputs']:
        raise ValueError('Incomplete or mismatched input control')
    if receipt['candidateBuildSha256']!=build_digest or receipt['runtime']!=runtime:
        raise ValueError('Mismatched candidate/runtime')
    if receipt['environment']!=dict(baseline['environment'],**VARIANTS[mode]):
        raise ValueError('Mismatched experimental conditions')
    if receipt['variantControllerSha256']!=sha(Path(__file__).with_name('startup_fixes_capture.py')):
        raise ValueError('Changed capture controller')


def assess(root,prior):
    build=root/'build.json';baseline=json.loads((prior/'off/run.json').read_text())
    receipts={m:json.loads((root/m/'run.json').read_text()) for m in VARIANTS}
    counts={};comparisons={}
    for mode,receipt in receipts.items():
        validate_receipt(receipt,baseline,mode,sha(build),receipts['off']['runtime'])
        folder=root/mode
        for name,digest in receipt['inputs'].items():
            if sha(folder/name)!=digest:raise ValueError('Changed input')
        for name,item in receipt['storage'].items():
            if logical_sha(folder/name)!=item['sha256']:raise ValueError('Changed captured stream')
        summary=runtime_summary(folder/'ngspice.log')
        if summary['count'] is None or summary['diagnostic'] or summary['sorry']:
            raise ValueError('Invalid complete control')
        counts[mode]=summary['count']
        with open_text(folder/'ngspice.log') as stream:
            initialization=[line.strip() for line in stream if line.startswith('HISTORY_INIT ')]
        expected=[] if VARIANTS[mode]['ROBOTRON_HISTORY_INIT']=='off' else [
            'HISTORY_INIT seed='+VARIANTS[mode].get('ROBOTRON_HISTORY_SEED','none')+' initialized=1 ports=69']
        if initialization!=expected:raise ValueError('Missing or duplicate history initialization')
        if not equal(root/'off/ngspice.log',folder/'ngspice.log',('FIRST_FETCH ','BUS_','SERIAL_')):
            raise ValueError('Changed firmware continuation')
    for mode in VARIANTS:
        reference='off' if mode in ('off','history') else 'fixed'
        folder=prior/reference;receipt=json.loads((folder/'run.json').read_text())
        if receipt['exitCode']!=0 or receipt['inputs']!=baseline['inputs']:
            raise ValueError('Invalid prior control')
        for name,item in receipt['storage'].items():
            if logical_sha(folder/name)!=item['sha256']:raise ValueError('Changed prior capture')
        summary=runtime_summary(folder/'ngspice.log')
        if summary['count'] is None or summary['diagnostic'] or summary['sorry']:
            raise ValueError('Invalid prior completion')
        comparisons[mode]=compare_raw(root/mode/'waveform.raw',folder/'waveform.raw',
                                      [counts[mode],summary['count']],20e-6,exact=True)
        if not equal(root/mode/'ngspice.log',folder/'ngspice.log',('FIRST_FETCH ','BUS_','SERIAL_')):
            raise ValueError('Changed prior firmware continuation')
    return {'waveformComparisons':comparisons,'sampleCounts':counts,
            'priorReceipts':{m:sha(prior/m/'run.json') for m in ('off','fixed')},
            'candidateBuildSha256':sha(build),'qualified':False,
            'scope':'Both opt-in fixes in one runtime: disabled and history-only controls match the earlier disabled waveform; staged-only and all combined allocation seeds match the earlier staged fix exactly. Complete bounded 20-us observer fixture, not the full startup/reset/repeat scenarios.',
            'notEstablished':['Full-window numerical convergence','Private event-state rollback across all scenarios','Physical device/load admission']}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--prior',type=Path);p.add_argument('--check-manifest',action='store_true');a=p.parse_args()
    if a.check_manifest:check(a.root)
    else:
        if not a.prior:p.error('Need prior staged-output report')
        result=assess(a.root,a.prior)
        (a.root/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))
