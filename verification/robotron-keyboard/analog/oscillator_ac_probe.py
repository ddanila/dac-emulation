#!/usr/bin/env python3
"""Measure closed-oscillator small-signal response at a matched observed transient plateau."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from circuit import load
from oscillator_probe import wiring
from oscillator_disturbance import SIGNALS, BUDGET
from failure_evidence import solver_diagnostic, capture
from ls00_transistor_probe import sha

HERE=Path(__file__).resolve().parent
NODES=SIGNALS[:-1]


def ac_rows(text):
    lines=text.splitlines()
    if not lines or lines[0].lower().split()!=['frequency']+[s.lower()for s in NODES for _ in range(2)]:
        raise ValueError('Unexpected complex AC columns')
    rows=[list(map(float,line.split()))for line in lines[1:]]
    if len(rows)!=361 or any(len(r)!=11 or not all(map(math.isfinite,r))for r in rows):
        raise ValueError('Invalid AC samples')
    if any(not math.isclose(r[0],10**(i/40),rel_tol=1e-10)for i,r in enumerate(rows)):
        raise ValueError('Incomplete or reordered AC frequency grid')
    return [(row[0],dict(zip(NODES,[complex(*row[i:i+2])for i in range(1,11,2)])))for row in rows]


def describe(value):
    return {'real':value.real,'imaginary':value.imag,'magnitude':abs(value),
            'phaseDegrees':math.degrees(math.atan2(value.imag,value.real))}


def summaries(rows):
    result=[]
    for frequency,values in rows:
        gains={}
        for name,output,input_ in [('first','v(n_OSC1)','v(n_OSC_RC)'),('second','v(n_OSC2)','v(n_OSC1)'),('buffer','v(n_CLK)','v(n_OSC2)')]:
            if abs(values[input_])<1e-15:raise ValueError('Unresolved response ratio denominator')
            gains[name]=describe(values[output]/values[input_])
        result.append({'frequencyHz':frequency,'nodeTransimpedanceOhms':{s:describe(v)for s,v in values.items()},'loadedResponseRatios':gains})
    return result


def reference_plateaus(directory,model_hash,connectivity,engine_hash):
    report=json.loads((directory/'assessment.json').read_text())
    if not report.get('completed') or report['modelSha256']!=model_hash or report['connectivitySha256']!=connectivity or report['engineSha256']!=engine_hash:
        raise ValueError('Transient reference is incomplete or mismatched')
    if sha(directory/'model.cir')!=model_hash:raise ValueError('Stale transient model')
    cases=[c for c in report['cases']if c['amplitudeAmps']==0]
    if len(cases)!=2 or len({c['stepSeconds']for c in cases})!=2 or not all(c['returnedToPlateau'] is True for c in cases):
        raise ValueError('Missing paired unforced plateaus')
    for case in cases:
        if not math.isfinite(case['stepSeconds']) or case['stepSeconds']<=0 or any(not math.isfinite(case['nodes'][s]['afterVolts'])for s in NODES):
            raise ValueError('Invalid transient plateau values')
        for filename,digest in case['artifacts'].items():
            if sha(directory/filename)!=digest:raise ValueError('Stale transient artifact')
    return cases


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',type=Path,required=True)
    p.add_argument('--transient',type=Path,required=True,help='Completed oscillator_disturbance capture')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--ngspice',default='ngspice')
    p.add_argument('--seed-transient-op',action='store_true',help='Use observed transient nodes as DC initial guesses, never voltage clamps')
    args=p.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    engine=Path(shutil.which(args.ngspice)or args.ngspice).resolve(strict=True)
    shutil.copyfile(args.model,out/'model.cir');(out/'spinit').write_text('* Pure SPICE AC diagnostic.\n')
    components,connectivity=load();lines,*_=wiring(components)
    report={'completed':False,'qualified':False,'modelSha256':sha(out/'model.cir'),'engineSha256':sha(engine),
        'connectivitySha256':connectivity,'transientAssessmentSha256':sha(args.transient/'assessment.json'),
        'scope':'Closed BR1 and complete reference oscillator including unused gate and reference CPU load. Unit AC current injects into OSC_RC; DC injection is zero. Ratios are loaded responses within the closed circuit, not open-loop gain, stability margins or a startup proof. Observed external-node plateau agreement does not prove identical internal junction states. Frequency coverage and generic device parameters do not establish physical bandwidth.',
        'seedTransientOp':args.seed_transient_op,'opComparisonBudgetVolts':BUDGET,'spinitSha256':sha(out/'spinit'),
        'sources':{f.name:sha(f)for f in [Path(__file__),HERE/'circuit.py',HERE/'oscillator_probe.py',HERE/'oscillator_disturbance.py',HERE/'failure_evidence.py',HERE/'ls00_transistor_probe.py']}}
    try:
        cases=reference_plateaus(args.transient,report['modelSha256'],connectivity,report['engineSha256'])
        seeds={s:cases[0]['nodes'][s]['afterVolts']for s in NODES} if args.seed_transient_op else {}
        report['operatingPointInitialGuessesVolts']=seeds
        hints=['.nodeset '+' '.join(s+'='+format(v,'.17g')for s,v in seeds.items())] if seeds else []
        (out/'probe.cir').write_text('\n'.join(['Closed oscillator AC diagnostic','.include model.cir','Vcc n_p5V 0 5','Iac 0 n_OSC_RC DC 0 AC 1','.temp 25','.options reltol=1e-8 vntol=1e-10 abstol=1e-14 gmin=1e-15',*lines,*hints,'.control','set numdgt=17','set wr_singlescale','set wr_vecnames','op','wrdata op.txt '+' '.join(NODES),'ac dec 40 1 1g','wrdata ac.txt '+' '.join(NODES),'quit','.endc','.end'])+'\n')
        with(out/'ngspice.log').open('w')as f:
            subprocess.run([str(engine),'-n','-b','probe.cir'],cwd=out,env=dict(os.environ,SPICE_SCRIPTS=str(out)),stdout=f,stderr=subprocess.STDOUT,check=True,timeout=60)
        if solver_diagnostic((out/'ngspice.log').read_text()):raise ValueError('Solver diagnostic')
        raw=(out/'op.txt').read_text().splitlines()
        if len(raw)!=2 or raw[0].lower().split()[1:]!=[s.lower()for s in NODES]:raise ValueError('Invalid OP columns')
        values=list(map(float,raw[1].split()))
        if len(values)!=6 or not all(map(math.isfinite,values)):raise ValueError('Invalid OP samples')
        op=dict(zip(NODES,values[1:]));report['operatingPointVolts']=op
        differences=[{'case':c['name'],'maximumDifferenceVolts':max(abs(op[s]-c['nodes'][s]['afterVolts'])for s in NODES)}for c in cases]
        report['transientPlateauComparisons']=differences
        if any(c['maximumDifferenceVolts']>BUDGET for c in differences):raise ValueError('DC branch differs from transient plateau')
        response=summaries(ac_rows((out/'ac.txt').read_text()))
        report['decadeSamples']=response[::40]
        report['inputImpedanceMagnitudeRangeOhms']=[min(r['nodeTransimpedanceOhms']['v(n_OSC_RC)']['magnitude']for r in response),max(r['nodeTransimpedanceOhms']['v(n_OSC_RC)']['magnitude']for r in response)]
        report['artifacts']={f.name:sha(f)for f in [out/'probe.cir',out/'ngspice.log',out/'op.txt',out/'ac.txt']}
        if sha(engine)!=report['engineSha256']:raise ValueError('Engine changed')
        report['completed']=True
    except Exception as error:
        report['error']=str(error)
        report['failureEvidence']=capture(out,['probe.cir','ngspice.log','op.txt','ac.txt'])
        raise
    finally:(out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
    print(out/'assessment.json')


if __name__=='__main__':main()
