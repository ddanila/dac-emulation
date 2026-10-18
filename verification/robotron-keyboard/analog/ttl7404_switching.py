#!/usr/bin/env python3
"""Explore the D104 switching load with explicit unsourced generator/diode assumptions."""
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
    limits=json.loads((HERE/'d104_limits.json').read_text())
    timing=limits['switching']
    maxima={'tPHL':timing['fallDelayMaxSeconds']*1e9,'tPLH':timing['riseDelayMaxSeconds']*1e9}
    report={'completed':False,'qualified':False,'scope':__doc__,
            'sources':{name:sha(HERE/name)for name in ('ttl7404_switching.py','ttl7404_nominal.cir','d104_limits.json','gate_switching_probe.py','failure_evidence.py')},
            'executableSha256':sha(executable),'spinitSha256':sha(args.out/'spinit'),
            'publishedFixture':timing,'deviceSource':limits['source'],
            'assumptions':{'generatorLowV':0,'generatorHighV':3,'sourceOhms':50,
                           'inputReverseBeta':.01,'fixtureDiodes':'Generic IS=1e-14 N=1 RS=1 CJO=0 TT=0; type not specified on reviewed sheet',
                           'refinementBudgetNs':.2,'minimumDelayScreenNs':0},
            'limitations':['RFT generator levels, source impedance, edge times and load-diode characteristics are not fully specified in the reviewed sheet.',
                           'Generic transistor storage and capacitance remain uncalibrated. Passing maximum-delay checks would not establish dynamic applicability.',
                           'Nonnegative delay is a diagnostic screen, not an additional RFT minimum-delay specification.'], 'cases':[]}
    try:
        for edge in (1,7,50):
            case={'inputEdgeNs':edge,'runs':[]};report['cases'].append(case)
            for step in (.1,.05):
                folder=args.out/f'{edge}ns-{step}ns';folder.mkdir()
                model=(HERE/'ttl7404_nominal.cir').read_text()
                deck=f'''D104 candidate in published diode load topology
{model}
.temp {timing['temperatureC']}
Vcc vp 0 {timing['supplyV']}
Vinput generator 0 PULSE(0 3 200n {edge}n {edge}n {400-edge}n 1u)
Rsource generator a 50
Xdut a y vp 0 TTL7404_NOMINAL input_br=.01
Rload vp load {timing['loadOhms']}
D1 load y FIXTURE_DIODE
D2 load d2 FIXTURE_DIODE
D3 d2 d3 FIXTURE_DIODE
D4 d3 0 FIXTURE_DIODE
.model FIXTURE_DIODE D(IS=1e-14 N=1 RS=1 CJO=0 TT=0)
Cload y 0 {timing['loadPf']}p
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
