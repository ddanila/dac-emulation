#!/usr/bin/env python3
"""Review same-tick output draining with isolated exact-tick controls."""
import argparse
import json
from pathlib import Path
from audit_log import complete, equal, records
from compare_firmware_io import sha as logical_sha
from postreset_startup_review import FIRMWARE
from raw_pair_review import compare_raw
from stop_board_review import startup_identity
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def conditions(base, mode):
    if mode not in ('off','tick','on','retry'):raise ValueError('Unknown mode')
    result=dict(base)
    if mode!='off':result['ROBOTRON_ABSOLUTE_TICKS']='1'
    if mode in ('on','retry'):result['ROBOTRON_DRAIN_TICK']='1'
    if mode=='retry':result.update(ROBOTRON_FORCE_NEWTON_REJECT='1',ROBOTRON_NEWTON_REJECT_START='0.000005')
    return result


def assess(root, producer):
    runs={n:json.loads((root/n/'run.json').read_text()) for n in ('baseline','off','tick','on','retry')}
    base=runs['baseline'];known=HERE/'reports/display-board/baseline/run.json'
    if sha(root/'baseline/run.json')!=sha(known):raise ValueError('Changed reviewed original baseline')
    build=json.loads((root/'candidate-build.json').read_text())
    def vpi(run):
        found=[d for d in run['externalDependencies'] if Path(d['path']).name=='ivlng.vpi']
        if len(found)!=1:raise ValueError('Ambiguous VPI')
        return found[0]
    old,new=vpi(base),vpi(runs['off'])
    if old==new or new['sha256']!=build['outputs']['ivlng.vpi']:raise ValueError('Missing distinct built candidate')
    expected_deck=(root/'baseline/io.cir').read_text()
    if expected_deck.count(old['path'])!=1:raise ValueError('Ambiguous VPI placement')
    expected_deck=expected_deck.replace(old['path'],new['path'])
    expected_deps=sorted([new if d==old else d for d in base['externalDependencies']],key=lambda d:d['path'])
    scans={};receipts={};startup=startup_identity(root/'baseline/ngspice.log')
    for mode,r in runs.items():
        folder=root/mode
        if not r['completed'] or r.get('error') or r['exitCode']!=0 or r['log']['exitCode']!=0:raise ValueError('Failed capture')
        if r['runtime']!=base['runtime'] or r['endSeconds']!=20e-6:raise ValueError('Changed runtime/window')
        if mode!='baseline':
            if r['mode']!=mode or r['producerSha256']!=sha(producer):raise ValueError('Changed producer/mode')
            if r['baselineReceiptSha256']!=sha(root/'baseline/run.json') or r['candidateBuildSha256']!=sha(root/'candidate-build.json'):raise ValueError('Changed provenance')
            if r['environment']!=conditions(base['environment'],mode) or r['externalDependencies']!=expected_deps:raise ValueError('Unmatched control')
            if r['runtimeEnvironment']!={'SPICE_SCRIPTS':str(Path(base['runtime']['spinit']['path']).parent)}:raise ValueError('Missing runtime selection')
            if (folder/'io.cir').read_text()!=expected_deck:raise ValueError('Changed circuit beyond VPI path')
        if set(r['inputs'])!=set(base['inputs']):raise ValueError('Changed input scope')
        for n,h in r['inputs'].items():
            if sha(folder/n)!=h or (n!='io.cir' and h!=base['inputs'][n]):raise ValueError('Changed input')
        for n,h in [('ngspice.log',r['log']['sha256']),('waveform.raw',r['storage']['waveform.raw']['sha256'])]:
            if logical_sha(folder/n)!=h:raise ValueError('Changed captured output')
        if startup_identity(folder/'ngspice.log')!=startup:raise ValueError('Changed initialized models')
        scans[mode]=complete(folder/'ngspice.log')
        if not scans[mode]['latchesMatch'] or not next(records(folder/'ngspice.log',('FIRST_FETCH ',)),None):raise ValueError('Missing valid firmware execution')
        faults=scans[mode]['faults']
        if len(faults)!=(1 if mode=='retry' else 0) or (faults and 'kind=newton ' not in faults[0]['record']):raise ValueError('Wrong forced rejection coverage')
        receipts[mode]=sha(folder/'run.json')
    comparisons={};firmware={}
    for label,left,right in [('disabled','baseline','off'),('exactTick','off','tick'),('outputDrain','tick','on'),('forcedRetry','on','retry')]:
        comparisons[label]=compare_raw(root/left/'waveform.raw',root/right/'waveform.raw',[scans[n]['count'] for n in (left,right)],20e-6,exact=label=='disabled')
        firmware[label]=equal(root/left/'ngspice.log',root/right/'ngspice.log',FIRMWARE)
    if not firmware['disabled']:raise ValueError('Disabled candidate changed firmware')
    return {'completed':True,'qualified':False,'disabledControlPassed':True,'comparisons':comparisons,
            'firmwareRecordsExactlyEqual':firmware,'logs':scans,'receipts':receipts,
            'scope':'Complete 20-us fixture, reset at 1 us, one forced Newton rejection after 5 us. Exact-tick and same-tick drain changes are measured separately, not waived. No three-level convergence or full post-reset claim.',
            'notEstablished':['ADC-enabled interaction','Full post-reset and longer-window refinements','Private HDL rollback and device applicability']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('root','producer','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args()
    with a.out.open('x') as f:json.dump(assess(a.root,a.producer),f,indent=2);f.write('\n')
