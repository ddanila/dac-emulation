#!/usr/bin/env python3
"""Diagnose finite-disturbance recovery of the complete reference oscillator."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from circuit import load
from oscillator_probe import wiring
from failure_evidence import solver_diagnostic
from ls00_transistor_probe import sha

HERE = Path(__file__).resolve().parent
SIGNALS = ['v(n_OSC_OUT)', 'v(n_CLK)', 'v(n_OSC_RC)', 'v(n_OSC1)', 'v(n_OSC2)', 'i(vsense)']
BUDGET = 1e-6


def summarize(rows, amplitude, step):
    if not math.isfinite(amplitude) or not math.isfinite(step) or step <= 0:
        raise ValueError('Invalid stimulus or timestep')
    if not rows or any(len(r) != 7 or not all(map(math.isfinite, r)) for r in rows):
        raise ValueError('Invalid transient samples')
    if not 0 <= rows[0][0] <= 1e-9 or rows[-1][0] < math.nextafter(20e-6, 0):
        raise ValueError('Incomplete transient endpoints')
    if any(not 0 < b[0]-a[0] <= step*1.00001 for a,b in zip(rows, rows[1:])):
        raise ValueError('Nonmonotonic or undersampled transient')
    before = [r for r in rows if 8e-6 <= r[0] <= 9e-6]
    pulse = [r for r in rows if 10.02e-6 <= r[0] <= 10.08e-6]
    after = [r for r in rows if 18e-6 <= r[0] <= 20e-6]
    if any(len(w) < 2 for w in [before, pulse, after]):
        raise ValueError('Missing comparison or stimulus window')
    if max(abs(r[-1]-amplitude) for r in pulse) > 1e-10 or max(abs(r[-1]) for r in before+after) > 1e-10:
        raise ValueError('Incorrect disturbance current')
    nodes = {}
    for i,signal in enumerate(SIGNALS[:-1],1):
        means = [math.fsum(r[i] for r in w)/len(w) for w in [before,after]]
        spans = [max(r[i] for r in w)-min(r[i] for r in w) for w in [before,after]]
        nodes[signal] = dict(beforeVolts=means[0], afterVolts=means[1], recoveryDifferenceVolts=abs(means[1]-means[0]),
                             beforeSpanVolts=spans[0], afterSpanVolts=spans[1],
                             fullRangeVolts=[min(r[i] for r in rows), max(r[i] for r in rows)])
    late = [r for r in rows if r[0] >= 12e-6]
    return {'nodes':nodes, 'lateClockRisingEdges':sum(a[2] < 2 <= b[2] for a,b in zip(late,late[1:])),
            'returnedToPlateau':all(n['recoveryDifferenceVolts'] <= BUDGET and
                max(n['beforeSpanVolts'],n['afterSpanVolts']) <= BUDGET for n in nodes.values())}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--ngspice',default='ngspice')
    args = p.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(args.model,out/'model.cir')
    (out/'spinit').write_text('* Pure SPICE diagnostic initialization.\n')
    engine=Path(shutil.which(args.ngspice) or args.ngspice).resolve(strict=True)
    components,connectivity=load();lines,_,_,_,_=wiring(components)
    report={'completed':False,'qualified':False,'connectivitySha256':connectivity,
        'scope':'Reference oscillator with closed BR1, fixed schematic values and ideal 10 ns supply ramp. A 100 ns current pulse at OSC_RC after 10 us probes finite-disturbance recovery. These injected stimuli are not specimen noise or a manufacturer startup test. Late edges and plateau comparisons do not qualify startup, global stability or phase convergence.',
        'currentConvention':'Positive current removes charge from OSC_RC; negative current injects charge.',
        'comparisonBudgetVolts':BUDGET,'modelSha256':sha(out/'model.cir'),'engineSha256':sha(engine),
        'spinitSha256':sha(out/'spinit'),
        'sources':{f.name:sha(f) for f in [Path(__file__),HERE/'oscillator_probe.py',HERE/'circuit.py',HERE/'failure_evidence.py',HERE/'ls00_transistor_probe.py']},
        'cases':[],'pairs':[]}
    try:
        for amplitude in [-.005,-.001,0,.001,.005]:
            pair=[]
            for step in [1e-9,.5e-9]:
                name=f'pulse-{amplitude:+g}A-{step:g}s';deck=out/(name+'.cir')
                deck.write_text('\n'.join(['Reference oscillator disturbance', '.include model.cir','.temp 25',
                    '.options reltol=1e-8 vntol=1e-10 abstol=1e-14 gmin=1e-15',
                    'Vcc n_p5V 0 PWL(0 0 10n 5)',*lines,'Vsense n_OSC_RC inject 0',
                    f'Idisturb inject 0 PWL(0 0 10u 0 10001n {amplitude:.17g} 10100n {amplitude:.17g} 10101n 0 20u 0)',
                    '.control','set numdgt=17','set wr_vecnames','set wr_singlescale',
                    f'tran {step:.17g} 20u 0 {step:.17g}',f'wrdata {name}.txt '+ ' '.join(SIGNALS),
                    'quit','.endc','.end'])+'\n')
                log=out/(name+'.log')
                with log.open('w') as stream:
                    subprocess.run([str(engine),'-n','-b',deck.name],cwd=out,
                        env=dict(os.environ,SPICE_SCRIPTS=str(out)),stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=120)
                if solver_diagnostic(log.read_text()):raise ValueError('Solver diagnostics: '+name)
                trace=out/(name+'.txt');raw=trace.read_text().splitlines()
                if raw[0].lower().split()[1:]!=[s.lower()for s in SIGNALS]:raise ValueError('Unexpected waveform columns')
                result=dict(name=name,amplitudeAmps=amplitude,stepSeconds=step,
                    **summarize([list(map(float,line.split()))for line in raw[1:]],amplitude,step),
                    artifacts={f.name:sha(f) for f in [deck,log,trace]})
                report['cases'].append(result);pair.append(result)
            difference=max(abs(pair[0]['nodes'][s][which]-pair[1]['nodes'][s][which]) for s in SIGNALS[:-1]for which in ['beforeVolts','afterVolts'])
            report['pairs'].append({'amplitudeAmps':amplitude,'maximumPlateauDifferenceVolts':difference,
                                   'plateausWithinNumericalBudget':difference<=BUDGET})
        if sha(engine)!=report['engineSha256']:raise ValueError('Engine changed during capture')
        report['completed']=True
    finally:(out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
    print(out/'assessment.json')


if __name__=='__main__':main()
