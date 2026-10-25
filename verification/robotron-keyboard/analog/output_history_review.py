#!/usr/bin/env python3
"""Review allocation-seed controls without promoting bounded captures to qualification."""
import argparse
import json
from pathlib import Path
from audit_log import scan, equal
from compare_firmware_io import sha as logical_sha
from output_history_capture import VARIANTS
from raw_pair_review import compare_raw
from test_output_history_init import probe
from trace_io import open_text
from ttl7406_probe import sha
PREFIX=('FIRST_FETCH ','BUS_','SERIAL_')


def compare(left,right,counts):
    try:return compare_raw(left,right,counts,20e-6,exact=True)
    except ValueError as exc:
        if not str(exc).startswith('Different raw sample at row '):raise
        return {'allSamplesExactlyEqual':False,'comparison':compare_raw(left,right,counts,20e-6)}


def assess(root,baseline):
    runs={mode:json.loads((root/mode/'run.json').read_text()) for mode in VARIANTS}
    base=json.loads((baseline/'run.json').read_text());runs['baseline']=base
    scans={}
    for mode,r in runs.items():
        folder=baseline if mode=='baseline' else root/mode
        if r['inputs']!=base['inputs']:raise ValueError('Different input fixture')
        for name,digest in r['inputs'].items():
            if sha(folder/name)!=digest:raise ValueError('Changed fixture input')
        for name,item in r['storage'].items():
            if logical_sha(folder/name)!=item['sha256']:raise ValueError('Changed captured stream')
        if mode!='baseline':
            expected=dict(base['environment'],**VARIANTS[mode])
            if r['environment']!=expected or r['runtime']!=runs['off']['runtime']:raise ValueError('Different capture conditions')
            with open_text(folder/'ngspice.log') as stream:initializers=[s.strip() for s in stream if s.startswith('HISTORY_INIT ')]
            required=[] if mode=='off' else ['HISTORY_INIT seed=%s initialized=%d ports=69'%(VARIANTS[mode].get('ROBOTRON_HISTORY_SEED','none'),VARIANTS[mode]['ROBOTRON_HISTORY_INIT']=='on')]
            if initializers!=required:raise ValueError('Missing or ambiguous initializer execution')
        scans[mode]=scan(folder/'ngspice.log')
        complete=r['exitCode']==0 and scans[mode]['count'] is not None and not scans[mode]['diagnostic'] and not scans[mode]['sorry']
        if mode!='dirty-one' and not complete:raise ValueError('Incomplete positive control')
    def pair(a,b):
        folders=[baseline if m=='baseline' else root/m for m in (a,b)]
        return {'waveform':compare(*(p/'waveform.raw' for p in folders),[scans[m]['count'] for m in (a,b)]),
                'firmwareExactlyEqual':equal(*(p/'ngspice.log' for p in folders),PREFIX)}
    baseline_control=pair('off','baseline')
    if not baseline_control['waveform']['allSamplesExactlyEqual'] or not baseline_control['firmwareExactlyEqual']:raise ValueError('Disabled candidate changed baseline')
    independence={m:pair('init',m) for m in ('init-zero','init-one')}
    if any(not p['waveform']['allSamplesExactlyEqual'] or not p['firmwareExactlyEqual'] for p in independence.values()):raise ValueError('Initialized result depends on allocation seed')
    dirty=scans['dirty-one'];dirty_complete=runs['dirty-one']['exitCode']==0 and dirty['count'] is not None and not dirty['diagnostic'] and not dirty['sorry']
    unit=probe()
    if unit!='0 1 0 0 0':raise ValueError('Partial-output control failed')
    return {'disabledBaseline':baseline_control,'initializedSeedControls':independence,
            'initializedVsOriginal':pair('off','init'),
            'dirtyHistoryControl':pair('off','dirty-one') if dirty_complete else {'completed':False,'logReview':dirty},
            'partialOutputProbe':{'result':unit,'meaning':'Untouched output depends on uninitialized history seed without repair; initialization preserves its declared initial low value under both seeds.'},
            'qualified':False,'scope':'Opt-in current output-history initialization. Bounded full-fixture seed controls plus actual accept_output code exercised by an isolated partial-output shim.',
            'notEstablished':['Natural allocator distribution or frequency of affected real runs','Full required firmware scenarios','Full startup dynamics, pending events, numerical convergence or physical model admission']}


def check(root):
    manifest=json.loads((root/'manifest.json').read_text())
    files={str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file() and p.name!='manifest.json'}
    if files!=manifest['files']:raise ValueError('Changed initializer evidence')
    for name,digest in manifest['sources'].items():
        if sha(Path(__file__).parent/name)!=digest:raise ValueError('Changed initializer source')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--baseline',type=Path);p.add_argument('--check-manifest',action='store_true');a=p.parse_args()
    if a.check_manifest:check(a.root)
    else:
        if not a.baseline:p.error('Need baseline')
        result=assess(a.root,a.baseline);(a.root/'assessment.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
