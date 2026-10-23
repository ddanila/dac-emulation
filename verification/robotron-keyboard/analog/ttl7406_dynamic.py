#!/usr/bin/env python3
"""Calibrate explicit 7406 storage hypotheses, then test withheld conditions.

This is a reference-model experiment, not an identified semiconductor model.
No live-board results enter the fit. Junction capacitances are hypotheses.
"""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

from failure_evidence import solver_diagnostic
from gate_switching_probe import crossing, delays, sha

HERE = Path(__file__).resolve().parent


def model(tf_ns, tr_ns, junction_pf):
    if any(not math.isfinite(v) or v <= 0 for v in (tf_ns, tr_ns, junction_pf)):
        raise ValueError('Dynamic parameters must be finite and positive')
    text = (HERE / 'ttl7406_nominal.cir').read_text()
    text = text[text.index('.subckt'):].replace('TTL7406_NOMINAL', 'TTL7406_DYNAMIC')
    text = text.replace('input_br=1', 'input_br=.01')
    # Apply the same unmeasured transit/capacitance hypothesis to every NPN.
    # CJC/CJE=1/2 is also an assumption, not extracted process information.
    extra = f' TF={tf_ns:.17g}n TR={tr_ns:.17g}n CJE={junction_pf:.17g}p CJC={junction_pf/2:.17g}p'
    text = '\n'.join(line[:-1] + extra + ')' if line.startswith('.model') and ' NPN(' in line else line
                     for line in text.splitlines()) + '\n'
    return '* Experimental calibrated storage; junction values and transistor uniformity are unmeasured.\n' + text


def run(folder, executable, env, model_text, circuit, command, signals):
    folder.mkdir(parents=True)
    (folder / 'model.cir').write_text(model_text)
    (folder / 'probe.cir').write_text('\n'.join([
        '7406 independent device fixture', '.include model.cir', '.temp 25', circuit,
        '.options reltol=1e-6 vntol=1e-9 abstol=1e-15', '.control',
        'set numdgt=17', 'set wr_singlescale', 'set wr_vecnames', command,
        'wrdata trace.txt ' + signals, 'quit', '.endc', '.end', '']))
    result = subprocess.run([str(executable), '-n', '-b', 'probe.cir'], cwd=folder,
                            env=env, capture_output=True, text=True, timeout=60)
    log = result.stdout + result.stderr
    (folder / 'ngspice.log').write_text(log)
    result.check_returncode()
    if solver_diagnostic(log):
        raise ValueError(solver_diagnostic(log))
    rows = [list(map(float, line.split())) for line in (folder / 'trace.txt').read_text().splitlines()[1:]]
    if not rows or any(not all(map(math.isfinite, row)) for row in rows):
        raise ValueError('Invalid device waveform')
    return rows


def switching(folder, executable, env, params, edge=1, step=.1, load=110, cap=15):
    fixture = load == 110 and cap == 15
    rows = run(folder, executable, env, model(**params), f'''
Vcc vp 0 5
Vinput generator 0 PULSE(0 3 200n {edge}n {edge}n {400-edge}n 3u)
Rsource generator a 50
Xdut a y vp 0 TTL7406_DYNAMIC
Rload vp y {load}
Cload y 0 {cap}p
''', f'tran {step}n {800 if fixture else 2000}n 0 {step}n', 'v(a) v(y)')
    if any(b[0]-a[0] > step*1e-9+1e-15 for a,b in zip(rows,rows[1:])):
        raise ValueError('Maximum step exceeded')
    if fixture:
        return delays(rows, {'tPHL':23, 'tPLH':15})
    result = {}
    for name,rising,start,end in [('tPHL',True,190e-9,590e-9),('tPLH',False,590e-9,1990e-9)]:
        source=crossing(rows,1,rising,start,end)
        target=crossing(rows,2,not rising,start,end)
        result[name]={'minimumNs':(target[0]-source[1])*1e9,'maximumNs':(target[1]-source[0])*1e9}
    return result


def objective(measured):
    return sum(((d['minimumNs']+d['maximumNs'])/2-target)**2
               for name,target in [('tPHL',15),('tPLH',10)] for d in [measured[name]])


def fit(folder, executable, env, junction):
    """Deterministic log-space pattern search; calibration fixture only."""
    history = []
    cache = {}
    def evaluate(tf, tr):
        key = (round(tf,12),round(tr,12))
        if key not in cache:
            params = dict(tf_ns=tf,tr_ns=tr,junction_pf=junction)
            trial = folder / f'trial-{len(history):03d}'
            measured = switching(trial, executable, env, params)
            entry = dict(parameters=params,delays=measured,objective=objective(measured))
            history.append(entry)
            cache[key] = entry
            # Retain search metadata, not hundreds of redundant waveforms.
            shutil.rmtree(trial)
        return cache[key]
    best = evaluate(1,1)
    for factor in (4,2,1.4,1.15,1.05):
        for _ in range(20):
            p = best['parameters']
            choices = [best]
            for key in ('tf_ns','tr_ns'):
                for scale in (1/factor,factor):
                    candidate = dict(p);candidate[key] *= scale
                    if .001 <= candidate[key] <= 100:
                        choices.append(evaluate(candidate['tf_ns'],candidate['tr_ns']))
            chosen = min(choices,key=lambda v:v['objective'])
            if chosen is best:
                break
            best = chosen
    return best,history


def dc_checks(folder, executable, env, params):
    results = []
    for case in json.loads((HERE/'ttl7406_limits.json').read_text())['cases']:
        rows = run(folder/case['name'],executable,env,model(**params),f'''
Vcc vp 0 {case['supplyVolts']}
Vin a 0 {case['inputVolts']}
Rload vp y {case['pullupOhms']}
Iload 0 y {case['injectedOutputAmps']}
Xdut a y vp 0 TTL7406_DYNAMIC
''','op','v(a) v(y) i(Vcc) i(Vin)')
        if len(rows)!=1 or len(rows[0])!=5:
            raise ValueError('Invalid DC result')
        r=rows[0]
        sample=dict(inputVolts=r[1],outputVolts=r[2],supplyAmps=-r[3],inputAmps=-r[4])
        value=sample[case['metric']]
        results.append(dict(name=case['name'],sample=sample,
                            withinLimit=case.get('minimum',-math.inf)<=value<=case.get('maximum',math.inf)))
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--ngspice',default='ngspice')
    args=parser.parse_args()
    args.out=args.out.resolve();args.out.mkdir(parents=True,exist_ok=False)
    executable=Path(shutil.which(args.ngspice) or args.ngspice).resolve()
    (args.out/'spinit').write_text('* Isolated device calibration.\n')
    env=dict(os.environ,SPICE_SCRIPTS=str(args.out))
    report=dict(completed=False,qualified=False,boardAdmission=False,
        deviceSource=json.loads((HERE/'ttl7406_switching_limits.json').read_text())['source'],
        executableSha256=sha(executable),
        sources={p:sha(HERE/p) for p in ('ttl7406_dynamic.py','ttl7406_nominal.cir','ttl7406_limits.json','ttl7406_switching_limits.json','gate_switching_probe.py','failure_evidence.py')},
        calibration={'edgeNs':1,'stepNs':.1,'targetsNs':{'tPHL':15,'tPLH':10},
                     'meaning':'Typical-delay least squares, not a tolerance or independent validation'},
        assumptions=['Uniform TF/TR/CJE/CJC for all transistors; CJC=CJE/2; generic diode unchanged.',
                     'Junction hypotheses are sensitivity cases, not measured values or a supported range.',
                     'No breakdown, package parasitics, temperature or process calibration.',
                     'Published limits apply to TI SN7406, not proof of the museum device.'],
        cases=[])
    try:
        for junction in (.5,2,5):
            folder=args.out/f'junction-{junction:g}pf'
            best,history=fit(folder/'search',executable,env,junction)
            params=best['parameters']
            (folder/'candidate.cir').write_text(model(**params))
            (folder/'search.json').write_text(json.dumps(history,indent=2)+'\n')
            case=dict(parameters=params,calibration=best,validation=[],dc=dc_checks(folder/'dc',executable,env,params))
            report['cases'].append(case)
            for edge in (1,7):
                measurements=[switching(folder/f'edge-{edge}-step-{step}',executable,env,params,edge,step) for step in (.1,.05)]
                difference=max(abs(measurements[0][n][k]-measurements[1][n][k]) for n in ('tPHL','tPLH') for k in ('minimumNs','maximumNs'))
                case['validation'].append(dict(edgeNs=edge,runs=measurements,
                    maximumBracketDifferenceNs=difference,converged=difference<=.2,
                    withinDelayScreen=all(d['withinDelayLimit'] for m in measurements for d in m.values())))
            # The board pullup is not the manufacturer's switching fixture.
            case['loadingSensitivity']=[dict(loadOhms=560,loadPf=cap,
                delays=switching(folder/f'load-{cap}pf',executable,env,params,load=560,cap=cap)) for cap in (15,100,1000)]
            case['selectedScreensPass']=all(d['withinLimit'] for d in case['dc']) and all(v['converged'] and v['withinDelayScreen'] for v in case['validation'])
        report['completed']=True
        report['nextGate']='Independent loading/storage evidence is needed to admit any fitted hypothesis; typical-delay fitting cannot establish board dynamics.'
        if sha(executable)!=report['executableSha256']:
            raise ValueError('Simulator changed')
    except Exception as error:
        report['error']=str(error)
        raise
    finally:
        report['artifacts']={str(p.relative_to(args.out)):sha(p) for p in sorted(args.out.rglob('*')) if p.is_file() and p.name!='report.json'}
        (args.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(args.out/'report.json')


if __name__=='__main__':
    main()
