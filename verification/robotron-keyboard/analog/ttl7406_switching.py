#!/usr/bin/env python3
"""Check the generic SN7406 candidate in the published TI switching fixture."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

from failure_evidence import solver_diagnostic
from gate_switching_probe import delays, sha

HERE=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--ngspice',default='ngspice')
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    executable=Path(shutil.which(args.ngspice) or args.ngspice).resolve()
    (args.out/'spinit').write_text('* No external initialization.\n')
    env=dict(os.environ,SPICE_SCRIPTS=str(args.out.resolve()))
    limits=json.loads((HERE/'ttl7406_switching_limits.json').read_text())
    timing=limits['switching']
    generator=limits['generator']
    maxima={'tPHL':timing['fallDelayMaxSeconds']*1e9,'tPLH':timing['riseDelayMaxSeconds']*1e9}
    report={'completed':False,'qualified':False,'scope':__doc__,
            'sources':{name:sha(HERE/name)for name in ('ttl7406_switching.py','ttl7406_nominal.cir','ttl7406_switching_limits.json','gate_switching_probe.py','failure_evidence.py')},
            'executableSha256':sha(executable),'spinitSha256':sha(args.out/'spinit'),
            'publishedGenerator':generator,'publishedFixture':timing,'deviceSource':limits['source'],
            'assumptions':{'generatorLowV':0,'generatorHighV':3,'sourceOhms':50,
                           'inputReverseBeta':.01,'pulseShape':'Linear ramps at the declared generator; output source impedance is explicit',
                           'refinementBudgetNs':.2,'minimumDelayScreenNs':0},
            'limitations':['Published fixture uses one output and one input transition per measurement; this probe isolates the rising and falling measurement windows.',
                           'Generic transistor storage and capacitance remain absent. Passing maximum-delay checks would not establish dynamic applicability.',
                           'Nonnegative delay is a diagnostic screen, not a TI minimum-delay specification; typical delays are references, not acceptance bounds.'], 'cases':[]}
    try:
        for edge in (1,7):
            case={'inputEdgeNs':edge,'runs':[]};report['cases'].append(case)
            for step in (.1,.05):
                folder=args.out/f'{edge}ns-{step}ns';folder.mkdir()
                model=(HERE/'ttl7406_nominal.cir').read_text()
                deck=f'''SN7406 candidate in published resistor/capacitor load topology
{model}
.temp {timing['temperatureC']}
Vcc vp 0 {timing['supplyV']}
Vinput generator 0 PULSE({generator['lowV']} {generator['highV']} 200n {edge}n {edge}n {400-edge}n 1u)
Rsource generator a {generator['sourceOhms']}
Xdut a y vp 0 TTL7406_NOMINAL input_br=.01
Rload vp y {timing['loadOhms']}
Cload y 0 {timing['loadPf']}p
.options reltol=1e-4 vntol=1e-7 abstol=1e-13
.control
set numdgt=17
set wr_singlescale
set wr_vecnames
tran {step}n 800n 0 {step}n
wrdata trace.txt v(a) v(y)
quit
.endc
.end
'''
                (folder/'probe.cir').write_text(deck)
                proc=subprocess.run([str(executable),'-n','-b','probe.cir'],cwd=folder,env=env,capture_output=True,text=True,timeout=60)
                log=proc.stdout+proc.stderr;(folder/'ngspice.log').write_text(log)
                proc.check_returncode()
                if solver_diagnostic(log):raise ValueError(solver_diagnostic(log))
                rows=[list(map(float,line.split()))for line in (folder/'trace.txt').read_text().splitlines()[1:]]
                if any(b[0]-a[0]>step*1e-9+1e-15 for a,b in zip(rows,rows[1:])):raise ValueError('Trace exceeds maximum step')
                measured=delays(rows,maxima)
                for name,values in measured.items():
                    typical=timing['fallDelayTypicalSeconds' if name=='tPHL' else 'riseDelayTypicalSeconds']*1e9
                    values['withinPublishedMaximum']=values['maximumNs']<=maxima[name]
                    values['typicalReferenceNs']=typical
                    values['differenceFromTypicalNs']=[values['minimumNs']-typical,values['maximumNs']-typical]
                case['runs'].append({'stepNs':step,'delays':measured,
                    'artifacts':{name:sha(folder/name)for name in ('probe.cir','trace.txt','ngspice.log')}})
            case['maximumBracketEndpointDifferenceNs']=max(abs(case['runs'][0]['delays'][name][key]-case['runs'][1]['delays'][name][key])for name in maxima for key in ('minimumNs','maximumNs'))
            case['converged']=case['maximumBracketEndpointDifferenceNs']<=report['assumptions']['refinementBudgetNs']
        if sha(executable)!=report['executableSha256']:raise ValueError('Simulator changed')
        report['completed']=True
        report['numericallyConverged']=all(c['converged']for c in report['cases'])
        report['withinDelayScreen']=all(d['withinDelayLimit']for c in report['cases']for r in c['runs']for d in r['delays'].values())
    except Exception as error:
        report['error']=str(error);raise
    finally:(args.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(args.out/'report.json')

if __name__=='__main__':main()
