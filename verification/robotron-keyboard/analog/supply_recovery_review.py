#!/usr/bin/env python3
"""Screen complete reset traces for a sampled reset sequence after supply recovery."""
import argparse
import json
import math
from pathlib import Path
from compare_firmware_io import sha as logical_sha
from reset_supply_observation import LIMITS
from trace_io import open_text
from ttl7406_probe import sha

HERE=Path(__file__).resolve().parent
SOURCES=('supply_recovery_review.py','reset_supply_observation.py','cpu_clock_limits.json','trace_io.py')


def observe(rows,end):
    if not math.isfinite(end) or end<=0:raise ValueError('Invalid required endpoint')
    supply=LIMITS['operatingConditions'];inputs=LIMITS['ordinaryInput']
    epochs=[];current=None;previous=None;count=0;max_gap=0;outside=0
    for row in rows:
        if len(row)!=8 or not all(map(math.isfinite,row)):raise ValueError('Invalid reset sample')
        t,vcc,_,reset,*_=row
        if previous is None:
            if t!=0:raise ValueError('Missing startup endpoint')
        elif t<=previous:raise ValueError('Non-increasing sample times')
        if previous is not None:max_gap=max(max_gap,t-previous)
        previous=t;count+=1
        valid=supply['supplyMinimumVolts']<=vcc<=supply['supplyMaximumVolts']
        if not valid:current=None;outside+=1;continue
        if current is None:
            current={'kind':'startup' if not epochs else 'recovery','firstSampleSeconds':t,'lastSampleSeconds':t,
                     'samples':0,'resetStates':dict(low=0,high=0,unknown=0,outsideInputRange=0),
                     'firstLowSeconds':None,'firstSubsequentHighSeconds':None}
            epochs.append(current)
        current['lastSampleSeconds']=t;current['samples']+=1
        if not inputs['minimumVolts']<=reset<=vcc+inputs['maximumSupplyOffsetVolts']:state='outsideInputRange'
        elif reset<=inputs['lowMaximumVolts']:state='low'
        elif reset>=inputs['highMinimumVolts']:state='high'
        else:state='unknown'
        current['resetStates'][state]+=1
        if state=='low' and current['firstLowSeconds'] is None:current['firstLowSeconds']=t
        if state=='high' and current['firstLowSeconds'] is not None and current['firstSubsequentHighSeconds'] is None:
            current['firstSubsequentHighSeconds']=t
    if count<2 or previous is None or abs(previous-end)>4*math.ulp(end):raise ValueError('Incomplete required window')
    for epoch in epochs:
        epoch['sampledLowThenHigh']=epoch['firstSubsequentHighSeconds'] is not None
    return {'samples':count,'outsideRatedSupplySamples':outside,'maximumSampleGapSeconds':max_gap,'validSupplyEpochs':epochs,
            'recoveryEpochsWithSampledResetSequence':sum(e['kind']=='recovery' and e['sampledLowThenHigh'] for e in epochs)}


def rows(path):
    with open_text(path) as stream:
        header=next(stream).split()
        if header[:4]!=['time','v(n_p5V)','v(n_RESET_OUT)','v(n_RESET_N)'] or len(header)!=8:
            raise ValueError('Changed reset observation layout')
        for line in stream:
            if line.strip():yield list(map(float,line.split()))


def assess(root):
    retained=json.loads((root/'retention.json').read_text())
    for name,digest in retained['files'].items():
        if sha(root/name)!=digest:raise ValueError('Changed retained reset evidence')
    report=json.loads((root/'report.json').read_text())
    stimulus=json.loads((root/'supply-stimulus.json').read_text());end=stimulus['pointsSecondsVolts'][-1][0]
    results=[]
    for run in report['runs']:
        directory=f'{"closed" if run["br2Closed"] else "isolated"}-{run["stepUs"]}us'
        trace=root/directory/'trace.txt'
        if logical_sha(trace)!=run['artifacts']['trace.txt']:raise ValueError('Changed complete reset waveform')
        observed=observe(rows(trace),end)
        if not any(e['kind']=='recovery' for e in observed['validSupplyEpochs']):raise ValueError('No supply recovery observed')
        results.append({'directory':directory,'br2Closed':run['br2Closed'],'stepUs':run['stepUs'],'observation':observed})
    closed=[e for r in results if r['br2Closed'] for e in r['observation']['validSupplyEpochs'] if e['kind']=='recovery']
    isolated=[e for r in results if not r['br2Closed'] for e in r['observation']['validSupplyEpochs'] if e['kind']=='recovery']
    return {'completed':True,'qualified':False,'runs':results,
            'allClosedRecoveriesLackSampledAssertion':bool(closed) and all(e['firstLowSeconds'] is None for e in closed),
            'allIsolatedRecoveriesRemainSampledLow':bool(isolated) and all(e['resetStates']['low']==e['samples'] for e in isolated),'sourceRetentionSha256':sha(root/'retention.json'),'sourceAssumptions':report['assumptions'],
            'sources':{n:sha(HERE/n) for n in SOURCES},
            'scope':'Necessary sampled reset-sequence screen on complete retained reset-subcircuit traces. No interpolation or inference of logic state below rated supply.',
            'interpretation':'A sampled low-then-high sequence is only a necessary reset witness, not a clock-duration or restart proof. With no qualified state-retention model, firmware continuing through undervoltage cannot establish a defined restart. Absence of a sampled reset does not exclude a pulse between samples.',
            'notEstablished':['Between-sample reset pulses','Reset duration in qualified CPU clocks','CPU state retention below rated supply','Post-recovery firmware execution','Full-board convergence','Physical device applicability']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result=assess(a.root)
    with a.out.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
