#!/usr/bin/env python3
"""Bound sampled RESET stability before complete CPU-clock voltage rises."""
import argparse
import hashlib
from itertools import zip_longest
import json
import math
from pathlib import Path
from clock_convergence import timestamp_uncertainty
from trace_io import open_binary
from ttl7406_probe import sha

HERE=Path(__file__).resolve().parent
SOURCES=('cpu_reset_setup_review.py','cpu_reset_limits.json','cpu_clock_limits.json','clock_convergence.py','trace_io.py')


def observe(samples,end,maximum_step_ns):
    if not math.isfinite(end) or end<=0 or not math.isfinite(maximum_step_ns) or maximum_step_ns<=0:raise ValueError('Invalid observation window/step')
    limits=json.loads((HERE/'cpu_clock_limits.json').read_text());reset=json.loads((HERE/'cpu_reset_limits.json').read_text())
    if reset['holdAfterRisingClockMinimumNs']!=0:raise ValueError('Nonzero hold needs a trailing observation interval')
    power,clock,pin=limits['operatingConditions'],limits['clockInput'],limits['ordinaryInput']
    required=reset['setupBeforeRisingClockMinimumNs'];previous=None;stable=None;stable_since=None;clock_low=None;epoch=None;streak=0
    result={'qualified':False,'samples':0,'requiredSetupNs':required,'supplyEpochs':[],
            'outsideSupplySamples':0,'clockRangeViolations':0,'resetRangeViolations':0,
            'rises':0,'setupObserved':{'low':0,'high':0},'setupNotEstablished':0,'firstNotEstablished':None}
    for t,clk,rst,vcc,unc in samples:
        if not all(map(math.isfinite,(t,clk,rst,vcc,unc))) or unc<0:raise ValueError('Invalid waveform sample')
        if previous is None:
            if t!=0:raise ValueError('Missing initial endpoint')
        elif t<previous[0] or t-previous[0]>maximum_step_ns*1e-9+unc+previous[1]:raise ValueError('Nonmonotonic time or excessive sample gap')
        previous=(t,unc);result['samples']+=1
        valid=power['supplyMinimumVolts']<=vcc<=power['supplyMaximumVolts']
        if not valid:
            result['outsideSupplySamples']+=1;epoch=None;stable=None;stable_since=None;clock_low=None;streak=0;continue
        if epoch is None:
            epoch={'firstSampleSeconds':t,'lastSampleSeconds':t,'rises':0,'maximumConsecutiveSetupLowRises':0}
            result['supplyEpochs'].append(epoch)
        epoch['lastSampleSeconds']=t
        reset_valid=pin['minimumVolts']<=rst<=vcc+pin['maximumSupplyOffsetVolts']
        result['resetRangeViolations']+=int(not reset_valid)
        state=('low' if rst<=pin['lowMaximumVolts'] else 'high' if rst>=pin['highMinimumVolts'] else None) if reset_valid else None
        if state!=stable:
            stable=state;stable_since=t+unc if state is not None else None;streak=0
        if not clock['minimumVolts']<=clk<=vcc+clock['maximumSupplyOffsetVolts']:
            result['clockRangeViolations']+=1;clock_low=None;streak=0;continue
        if clk<=clock['lowMaximumVolts']:
            clock_low=t-unc
        elif clk>=vcc-clock['highMinimumSupplyDropVolts'] and clock_low is not None:
            earliest,latest=clock_low,t+unc;clock_low=None
            result['rises']+=1;epoch['rises']+=1
            # No interpolation: reset must be sampled in one valid state since
            # before the earliest possible rise, through the latest rise sample.
            lower=None if stable_since is None else max(0.,earliest-stable_since)*1e9
            established=lower is not None and lower>=required
            if established:result['setupObserved'][state]+=1
            else:
                result['setupNotEstablished']+=1
                if result['firstNotEstablished'] is None:
                    result['firstNotEstablished']={'clockRiseBracketSeconds':[earliest,latest],
                        'resetState':state,'stableSinceLatestSeconds':stable_since,'setupLowerNs':lower}
            streak=streak+1 if established and state=='low' else 0
            epoch['maximumConsecutiveSetupLowRises']=max(epoch['maximumConsecutiveSetupLowRises'],streak)
    if previous is None or abs(previous[0]-end)>max(previous[1],4*math.ulp(end)):raise ValueError('Incomplete required window')
    result['scope']='Sample-based stability bounds using complete low-to-high clock-voltage excursions and contiguous rated-supply intervals. No interpolation or hidden-pulse exclusion.'
    result['notEstablished']=['Clock pulse-width and slew qualification','Minimum active reset duration','First instruction phase after reset release','CPU undervoltage state retention','Full-board or specimen qualification']
    return result


def assess(root):
    report=json.loads((root/'report.json').read_text());window=report['assumptions']['traceWindowSeconds']
    if window[0]!=0:raise ValueError('Need complete startup-inclusive capture')
    if sha(root/'boot.cir')!=report['deckSha256']:raise ValueError('Changed source deck')
    digests=[hashlib.sha256(),hashlib.sha256()];counts=[0,0]
    def samples():
        with open_binary(root/'trace.txt') as clocks,open_binary(root/'supply-trace.txt') as supply:
            headers=[clocks.readline(),supply.readline()]
            expected=[['time',*report['traceSignals']],['time',report['supplyTraceSignal']]]
            for h,d,names in zip(headers,digests,expected):
                d.update(h)
                if h.decode('ascii').split()!=names:raise ValueError('Changed observation layout')
            for a,b in zip_longest(clocks,supply):
                if a is None or b is None:raise ValueError('Different waveform lengths')
                digests[0].update(a);digests[1].update(b)
                aa,bb=a.decode('ascii').split(),b.decode('ascii').split();c,r=list(map(float,aa)),list(map(float,bb))
                if len(c)!=5 or len(r)!=2 or c[0]!=r[0] or not all(map(math.isfinite,c+r)):raise ValueError('Unaligned/invalid observations')
                counts[0]+=1;counts[1]+=1
                yield c[0],c[1],c[2],r[1],max(timestamp_uncertainty(aa[0],c[0]),timestamp_uncertainty(bb[0],r[0]))
    result=observe(samples(),window[1],report['assumptions']['maximumStepNs'])
    if [d.hexdigest() for d in digests]!=[report['traceSha256'],report['supplyTraceSha256']]:raise ValueError('Changed complete source waveform')
    if counts[0]!=report['waveformRows']:raise ValueError('Changed complete sample count')
    result.update(completed=True,sourceReportSha256=sha(root/'report.json'),sourceDeckSha256=report['deckSha256'],
                  sourceWaveforms={'trace.txt':report['traceSha256'],'supply-trace.txt':report['supplyTraceSha256']},
                  sources={n:sha(HERE/n) for n in SOURCES})
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result=assess(a.root)
    with a.out.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
