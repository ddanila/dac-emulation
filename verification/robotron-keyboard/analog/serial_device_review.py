#!/usr/bin/env python3
"""Review internal serial-driver observations against an unchanged live control."""
import argparse
import hashlib
import itertools
import json
import lzma
import math
import re
from pathlib import Path

from gate_switching_probe import sha
from network_trace import PHYSICAL_SIGNALS
from network_refinement_review import events, artifact, text_file
from serial_device_trace import SIGNALS

HERE=Path(__file__).resolve().parent


def opened(path):
    return lzma.open(path,'rt') if path.suffix=='.xz' else path.open()


def digest_text(path):
    h=hashlib.sha256()
    with opened(path) as stream:
        for line in stream:h.update(line.encode())
    return h.hexdigest()


def samples(path, signals):
    with opened(path) as stream:
        if next(stream).split()!=['time',*signals]:raise ValueError('Unexpected trace header')
        previous=-1
        for line in stream:
            row=list(map(float,line.split()))
            if len(row)!=1+len(signals) or not all(map(math.isfinite,row)) or row[0]<=previous:
                raise ValueError('Invalid observation trace')
            previous=row[0]
            yield row


def review(run,baseline):
    receipt=json.loads((run/'run.json').read_text())
    if receipt['exitCode'] or receipt['timedOut'] or receipt['solverDiagnostic'] or receipt['stopNs']!=1160000:
        raise ValueError('Incomplete or failing live control')
    if sha(run/'io.cir')!=receipt['deckSha256']:raise ValueError('Changed live deck')
    path=artifact(run,'network_witness.txt');internal=artifact(run,'serial_device.txt')
    base=artifact(baseline,'network_witness.txt')
    ranges={s:[math.inf,-math.inf] for s in SIGNALS}
    worst=None;count=0;max_kcl=0;max_base_kcl=0
    peak_energy=0;last=None
    for n,q in itertools.zip_longest(samples(path,PHYSICAL_SIGNALS),samples(internal,SIGNALS)):
        if n is None or q is None or n[0]!=q[0]:raise ValueError('Unaligned device observations')
        last=n[0]
        if n[0]<.001:continue
        count+=1
        for signal,value in zip(SIGNALS,q[1:]):
            ranges[signal][0]=min(ranges[signal][0],value)
            ranges[signal][1]=max(ranges[signal][1],value)
        # Positive Q collector current enters the device. L1.4 leaves data output.
        max_kcl=max(max_kcl,abs((n[1]-n[3])/560-n[15]-q[1]))
        # VBE of the output transistor is its base voltage (emitter is ground).
        max_base_kcl=max(max_base_kcl,abs((n[1]-q[4])/1600-q[2]-q[7]))
        peak_energy=max(peak_energy,.5e-6*n[15]**2)
        if worst is None or n[3]<worst['network']['v(n_TA_DATEN)']:
            worst=dict(timeSeconds=n[0],network=dict(zip(PHYSICAL_SIGNALS,n[1:])),device=dict(zip(SIGNALS,q[1:])))
    if not count or abs(last-.00116)>1e-15:raise ValueError('Incomplete observation interval')
    log=text_file(artifact(run,'ngspice.log'))
    ownership=[(int(t),low,high) for t,low,high in re.findall(r'^BUS_DRIVE (\d+) ([01x]{24}) ([01x]{24})$',log,re.M) if int(t)*1e-12<=worst['timeSeconds']]
    if not ownership:raise ValueError('Missing bus ownership at excursion')
    time,low,high=ownership[-1]
    worst['lastSampledBusOwnership']=dict(timeSeconds=time*1e-12,
        scope='Drive intent at the preceding read sample; not a continuous ownership observation at the voltage minimum.',
        d0={name:dict(low=low[-1-bit],high=high[-1-bit]) for name,bit in (('CPU',0),('ROM',8),('latch',16))})
    current=events(log)
    control=events(text_file(artifact(baseline,'ngspice.log')))
    return dict(completed=True,qualified=False,boardAdmission=False,
        sourceSha256=sha(Path(__file__)),observerSha256=sha(HERE/'serial_device_trace.py'),
        baselineRunSha256=sha(baseline/'run.json'),runSha256=sha(run/'run.json'),
        networkByteIdenticalToControl=digest_text(path)==digest_text(base),
        firmwareMatchesControl=current['samples']==control['samples'] and current['latchesMatch'],
        intervalSeconds=[.001,last],samples=count,internalRanges=ranges,atMinimum=worst,
        maximumOutputKclResidualA=max_kcl,maximumBaseKclResidualA=max_base_kcl,
        currentBalanceScreen=dict(budgetA=1e-6,outputPassed=max_kcl<=1e-6,basePassed=max_base_kcl<=1e-6,
            scope='Additional diagnostic consistency screen using reported transistor states; not a waiver or replacement of board refinement requirements.'),
        peakDataFilterEnergyJ=peak_energy,
        dataCollectorExceedsPublishedSinkTestCurrent=ranges['@q.xdata.qoutput[ic]'][1]>.04,
        boundary='Post-reset sampled device state. Recommended 40 mA IOL is not an independently specified transient safe-operating-area curve. Reverse operation and charge follow generic fitted NPN parameters, not measured SN7406 recovery. Unchanged observations establish model causality, not hardware accuracy.',
        artifacts={str(p.name):sha(p) for p in (run/'io.cir',run/'run.json',path,internal,artifact(run,'ngspice.log'))})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.write_text(json.dumps(review(a.run,a.baseline),indent=2)+'\n')
