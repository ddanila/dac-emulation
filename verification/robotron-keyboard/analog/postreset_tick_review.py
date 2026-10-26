#!/usr/bin/env python3
"""Review full absolute-tick refinements and unchanged disabled/retry controls."""
import argparse
import json
from pathlib import Path
from audit_log import equal
from compare_firmware_io import sha as logical_sha
from postreset_tick_capture import SOURCES,experiment
from postreset_startup_review import END,FIRMWARE,inspect_log
from postreset_refinement_review import voltage_gate
from raw_pair_review import compare_raw
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def validate(receipt,base,mode,step,baseline_sha,build_sha,bounded_sha):
    if not receipt.get('completed') or receipt.get('error') or receipt.get('exitCode')!=0 or receipt['log']['exitCode']!=0:
        raise ValueError('Incomplete capture')
    if (receipt['mode'],receipt['stepNs'],receipt['endSeconds'])!=(mode,step,END):raise ValueError('Changed capture scope')
    for key,value in [('runtime',base['runtime']),('baselineReceiptSha256',baseline_sha),('candidateBuildSha256',build_sha),('boundedAssessmentSha256',bounded_sha)]:
        if receipt[key]!=value:raise ValueError('Changed '+key)
    if receipt['runtimeEnvironment']!={'SPICE_SCRIPTS':str(Path(base['runtime']['spinit']['path']).parent)}:raise ValueError('Missing XSPICE selection')
    if receipt['sources']!={n:sha(HERE/n) for n in SOURCES}:raise ValueError('Changed capture sources')
    if set(receipt['inputs'])!=set(base['inputs']) or set(receipt['storage'])!={'waveform.raw'}:raise ValueError('Changed input/output scope')
    for measured,limit in [('bytes','logicalLogBytes'),('compressedBytes','compressedLogBytes')]:
        if not 0<receipt['log'][measured]<=receipt['limits'][limit]:raise ValueError('Exceeded capture budget')


def assess(source,folders):
    base=json.loads((source/'run.json').read_text());base_sha=sha(source/'run.json')
    if base_sha!=sha(HERE/'reports/postreset-adc/25/run.json'):raise ValueError('Changed original baseline')
    off=folders['off'];off_run=json.loads((off/'run.json').read_text())
    build_sha=sha(off/'candidate-build.json');bounded_sha=sha(off/'bounded-assessment.json')
    build=json.loads((off/'candidate-build.json').read_text())
    def vpi(run):
        found=[d for d in run['externalDependencies'] if Path(d['path']).name=='ivlng.vpi']
        if len(found)!=1:raise ValueError('Ambiguous VPI dependency')
        return found[0]
    old,new=vpi(base),vpi(off_run)
    if old==new or new['sha256']!=build['outputs']['ivlng.vpi']:raise ValueError('Missing candidate build')
    deps=sorted([new if d==old else d for d in base['externalDependencies']],key=lambda d:d['path'])
    scans={'baseline':inspect_log(source/'ngspice.log','combined')};receipts={}
    for n,h in base['inputs'].items():
        if sha(source/n)!=h:raise ValueError('Changed baseline input')
    for n,h in [('ngspice.log',base['log']['sha256']),('waveform.raw',base['storage']['waveform.raw']['sha256'])]:
        if logical_sha(source/n)!=h:raise ValueError('Changed baseline output')
    spec={'off':('off',25),'coarse':('on',25),'fine':('on',12.5),'finest':('on',6.25),'retry':('retry',25)}
    for label,(mode,step) in spec.items():
        folder=folders[label];r=json.loads((folder/'run.json').read_text())
        validate(r,base,mode,step,base_sha,build_sha,bounded_sha)
        if sha(folder/'candidate-build.json')!=build_sha or sha(folder/'bounded-assessment.json')!=bounded_sha:raise ValueError('Changed build/control receipt')
        deck,env=experiment((source/'io.cir').read_text(),base['environment'],old['path'],new['path'],mode,step)
        if (folder/'io.cir').read_text()!=deck or r['environment']!=env or r['externalDependencies']!=deps:raise ValueError('Unmatched experiment')
        for n,h in r['inputs'].items():
            if sha(folder/n)!=h or (n!='io.cir' and h!=base['inputs'][n]):raise ValueError('Changed input')
        for n,h in [('ngspice.log',r['log']['sha256']),('waveform.raw',r['storage']['waveform.raw']['sha256'])]:
            if logical_sha(folder/n)!=h:raise ValueError('Changed output')
        scans[label]=inspect_log(folder/'ngspice.log','retry' if mode=='retry' else 'combined');receipts[label]=sha(folder/'run.json')
    all_folders=dict(folders,baseline=source);comparisons={};firmware={}
    for label,left,right in [('disabled','baseline','off'),('enabledEffect','off','coarse'),('coarseFine','coarse','fine'),('fineFinest','fine','finest'),('forcedRetry','coarse','retry')]:
        comparisons[label]=compare_raw(all_folders[left]/'waveform.raw',all_folders[right]/'waveform.raw',[scans[n]['count'] for n in (left,right)],END,exact=label=='disabled')
        firmware[label]=equal(all_folders[left]/'ngspice.log',all_folders[right]/'ngspice.log',FIRMWARE)
    if not firmware['disabled']:raise ValueError('Disabled candidate changed firmware')
    gate=voltage_gate(comparisons['coarseFine'],comparisons['fineFinest'])
    return {'completed':True,'qualified':False,'disabledControlPassed':True,
            'refinementGatePassed':gate['passed'] and firmware['coarseFine'] and firmware['fineFinest'],
            'voltageGate':gate,'comparisons':comparisons,'firmwareRecordsExactlyEqual':firmware,
            'logs':scans,'receipts':receipts,'baselineReceiptSha256':base_sha,'reviewerSha256':sha(Path(__file__)),
            'scope':'Complete 1.16-ms ADC-enabled post-reset controls and three timestep levels on absolute time; unchanged 10-mV/non-growth gate. Baseline timing changes and forced-retry effects are reported separately, not waived.',
            'notEstablished':['Acceptance of changed baseline timing','Complete private-HDL rollback','Startup, supply recovery and full-repeat qualification','Device/load applicability']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','off','coarse','fine','finest','retry','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();r=assess(a.source,{n:getattr(a,n) for n in ('off','coarse','fine','finest','retry')})
    with a.out.open('x') as f:json.dump(r,f,indent=2);f.write('\n')
