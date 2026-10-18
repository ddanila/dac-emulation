#!/usr/bin/env python3
"""Inspect oscillator DC transfer and bias; does not qualify startup or loop stability."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

from circuit import load
from failure_evidence import solver_diagnostic
from oscillator_probe import wiring

HERE=Path(__file__).resolve().parent


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def equilibria(rows):
    result=[]
    for a,b in zip(rows,rows[1:]):
        if a[4]==b[4]==0:raise ValueError('Ambiguous zero-current interval')
        if a[4]==0 or a[4]*b[4]<0 or (b is rows[-1] and b[4]==0):
            fraction=-a[4]/(b[4]-a[4]);point=[x+fraction*(y-x)for x,y in zip(a,b)]
            slopes=[(b[i]-a[i])/(b[0]-a[0])for i in [1,2]]
            result.append({'inputBracketVolts':[a[0],b[0]],
                'interpolatedVolts':dict(zip(['oscRc','osc1','osc2','clock'],point[:4])),
                'localSlopes':{'osc1VsRc':slopes[0],'osc2VsRc':slopes[1],
                               'osc2VsOsc1':slopes[1]/slopes[0] if slopes[0] else None}})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--ngspice',default='ngspice')
    args=p.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    engine=Path(shutil.which(args.ngspice) or args.ngspice).resolve(strict=True)
    shutil.copyfile(args.model,out/'model.cir')
    (out/'spinit').write_text('* Pure SPICE DC fixture.\n')
    env=dict(os.environ,SPICE_SCRIPTS=str(out))
    components,connectivity=load();lines,_,_,_,_=wiring(components)
    report={'completed':False,'qualified':False,'connectivitySha256':connectivity,
        'scope':'DC sweep clamps OSC_RC while retaining schematic loading and feedback resistor. Input-source zero current identifies equilibrium candidates. Local DC slopes are diagnostic, not AC loop-gain or startup proof.',
        'engineSha256':sha(engine),'sources':{x.name:sha(x) for x in [Path(__file__),HERE/'oscillator_probe.py',HERE/'circuit.py',HERE/'failure_evidence.py',args.model]},
        'spinitSha256':sha(out/'spinit'),'cases':[]}
    try:
        for name,step in [('coarse',.0001),('fine',.00005)]:
            deck=out/(name+'.cir')
            deck.write_text('\n'.join(['Reference oscillator DC transfer', '.include model.cir',
                '.options reltol=1e-8 vntol=1e-10 abstol=1e-14','.temp 25','Vcc n_p5V 0 5',
                'Vinput n_OSC_RC 0 0',*lines,'.control','set numdgt=17','set wr_singlescale','set wr_vecnames',
                f'dc Vinput 0 {3+step} {step}',f'wrdata {name}.txt v(n_OSC1) v(n_OSC2) v(n_OSC_OUT) i(Vinput)',
                'quit','.endc','.end'])+'\n')
            log=out/(name+'.log')
            with log.open('w') as f:
                run=subprocess.run([str(engine),'-n','-b',deck.name],cwd=out,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=60)
            run.check_returncode()
            if solver_diagnostic(log.read_text()):raise ValueError('Solver diagnostics: '+name)
            trace=out/(name+'.txt');raw=trace.read_text().splitlines()
            if raw[0].split()[1:]!=['v(n_OSC1)','v(n_OSC2)','v(n_OSC_OUT)','i(Vinput)']:raise ValueError('Unexpected sweep columns')
            rows=[list(map(float,l.split())) for l in raw[1:]]
            if not rows or any(len(r)!=5 or not all(map(math.isfinite,r))for r in rows):raise ValueError('Invalid sweep')
            if abs(rows[0][0])>1e-12 or not 3-1e-9 <= rows[-1][0] <= 3+step+1e-9:raise ValueError('Incomplete DC sweep')
            if any(b[0]<=a[0] or b[0]-a[0]>step+1e-9 for a,b in zip(rows,rows[1:])):raise ValueError('Nonmonotonic/incomplete sweep')
            roots=equilibria(rows)
            report['cases'].append({'name':name,'stepVolts':step,'equilibria':roots,
                'artifacts':{x.name:sha(x)for x in [deck,log,trace]}})
        if sha(engine)!=report['engineSha256']:raise ValueError('Engine changed during probe')
        report['completed']=True
    finally:(out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
    print(out/'assessment.json')


if __name__=='__main__':main()
