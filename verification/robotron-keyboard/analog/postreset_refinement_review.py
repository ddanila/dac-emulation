#!/usr/bin/env python3
"""Review full combined-fix timestep refinements and their matched controls."""
import argparse
import json
import math
from pathlib import Path
from audit_log import equal
from compare_firmware_io import sha as logical_sha
from postreset_refinement_capture import SOURCES, refined_deck
from postreset_startup_review import END, FIRMWARE, assess as assess_controls, inspect_log
from raw_pair_review import compare_raw
from ttl7406_probe import sha


def voltage_gate(previous, finest):
    a,b=previous['signals'],finest['signals']
    if not a or set(a)!=set(b): raise ValueError('Changed observation scope')
    failures={}; voltages=0
    for name,x in a.items():
        y=b[name]
        if x['unit']!=y['unit'] or x['unit'] not in ('V','A'): raise ValueError('Changed signal units')
        old,new=x['maximumAbsoluteDifference'],y['maximumAbsoluteDifference']
        if any(not math.isfinite(v) or v<0 for v in (old,new)): raise ValueError('Invalid difference')
        if x['unit']=='V':
            voltages+=1
            reasons=[]
            if new>.01: reasons.append('Exceeds 10 mV')
            if new>old: reasons.append('Difference grows under refinement')
            if reasons: failures[name]={'reasons':reasons,'previousV':old,'finestV':new}
    if not voltages: raise ValueError('No voltage observations')
    return {'passed':not failures,'limitV':.01,'failures':failures}


def validate_refinement(receipt, control, coarse_digest, source_digest, step):
    if receipt.get('completed') is not True or receipt.get('error') or receipt.get('exitCode')!=0:
        raise ValueError('Incomplete refinement')
    if receipt['stepNs']!=step or receipt['endSeconds']!=END:
        raise ValueError('Changed step or window')
    for key in ('runtime','environment','externalDependencies','candidateBuildSha256'):
        if receipt[key]!=control[key]: raise ValueError('Changed '+key)
    if receipt['originalInputs']!=control['inputs'] or receipt['coarseRunSha256']!=coarse_digest or receipt['sourceRunSha256']!=source_digest:
        raise ValueError('Changed control provenance')
    if receipt['sources']!={n:sha(Path(__file__).with_name(n)) for n in SOURCES}:
        raise ValueError('Changed capture sources')
    if set(receipt['inputs'])!=set(control['inputs']) or set(receipt['storage'])!={'waveform.raw'}:
        raise ValueError('Changed input or output scope')
    if receipt['log']['exitCode']!=0: raise ValueError('Failed log producer')
    for measured,limit in (('bytes','logicalLogBytes'),('compressedBytes','compressedLogBytes')):
        if not 0<receipt['log'][measured]<=receipt['limits'][limit]: raise ValueError('Exceeded log budget')


def assess(source,off,coarse,retry,fine,finest):
    # Recheck the complete disabled baseline and forced-retry evidence, not just
    # a previous assessment's success flag.
    controls=assess_controls(source,off,coarse,retry)
    control=json.loads((coarse/'run.json').read_text())
    scans=[controls['logs']['combined']]; receipts=[]
    for step,folder in ((12.5,fine),(6.25,finest)):
        receipt=json.loads((folder/'run.json').read_text())
        validate_refinement(receipt,control,sha(coarse/'run.json'),sha(source/'run.json'),step)
        expected=refined_deck((coarse/'io.cir').read_text(),step)
        if (folder/'io.cir').read_text()!=expected: raise ValueError('Changed refinement circuit or stimulus')
        for name,digest in receipt['inputs'].items():
            if sha(folder/name)!=digest: raise ValueError('Changed retained input')
            if name!='io.cir' and digest!=control['inputs'][name]: raise ValueError('Changed firmware input')
        if sha(folder/'build.json')!=control['candidateBuildSha256']: raise ValueError('Changed model manifest')
        for name,digest in (('waveform.raw',receipt['storage']['waveform.raw']['sha256']),('ngspice.log',receipt['log']['sha256'])):
            if logical_sha(folder/name)!=digest: raise ValueError('Changed retained '+name)
        scans.append(inspect_log(folder/'ngspice.log','combined'));receipts.append(sha(folder/'run.json'))
    folders=(coarse,fine,finest)
    pairs=[compare_raw(folders[i]/'waveform.raw',folders[i+1]/'waveform.raw',
                       [scans[i]['count'],scans[i+1]['count']],END) for i in range(2)]
    firmware=[equal(folders[i]/'ngspice.log',folders[i+1]/'ngspice.log',FIRMWARE) for i in range(2)]
    gate=voltage_gate(*pairs)
    accepted=gate['passed'] and all(firmware) and all(controls['firmwareRecordsExactlyEqual'].values())
    return {'completed':True,'qualified':False,'numericalGatePassed':accepted,'voltageGate':gate,
            'stepsNs':[25,12.5,6.25],'comparisons':pairs,'firmwareRecordsExactlyEqual':firmware,
            'controls':controls,'refinementRunSha256':receipts,'reviewerSha256':sha(Path(__file__)),
            'scope':'Complete post-reset window on both absolute-time grids; every observed voltage, no alignment or exclusions.',
            'notEstablished':['Startup and supply recovery','Full-repeat qualification','Device/load admission','Specimen agreement']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','off','coarse','retry','fine','finest','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args(); result=assess(a.source,a.off,a.coarse,a.retry,a.fine,a.finest)
    with a.out.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
