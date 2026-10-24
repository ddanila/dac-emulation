#!/usr/bin/env python3
"""Replay retained startup time partitions through the original single-bit DAC."""
import argparse
import hashlib
import json
import math
import subprocess
import tempfile
from decimal import Decimal as D, localcontext
from pathlib import Path
from host_waveform_comparison import rows
from compare_firmware_io import sha

HERE=Path(__file__).resolve().parent
MAIN=r'''
int main(int argc,char **argv) {
 assert(argc==2);
 double t, previous=0; const double changed=strtod(argv[1],NULL);
 unsetenv("ROBOTRON_DAC_BREAKPOINTS");
 times[1]=0;
 while(scanf("%lf",&t)==1) {
  times[0]=t;
  Digital_State_t old=times[1]<changed?ZERO:ONE;
  Digital_State_t now=t<changed?ZERO:ONE;
  previous=evaluate(old,now,changed,previous);
  printf("%.17g\n",previous);
  times[1]=t;
 }
 return 0;
}
'''


def exact_ramp(time):
    with localcontext() as c:
        c.prec=64
        return max(D(0),min(D(5),(D.from_float(time)-D.from_float(1e-8))*D(5000000000)))


def build(runs,evidence):
    fixture=HERE/'fixtures/ngspice-47/dac_bridge.mod'
    original=fixture.read_text()
    if sha(fixture)!=json.loads((fixture.parent/'dac-source.json').read_text())['sha256']:
        raise ValueError('Changed pinned evaluator')
    start=original.index('        /* Multiple single-bit conversions. */')
    end=original.index('\n        break;\n\n    default:',start)
    harness=(HERE/'fixtures/dac_ramp_harness.c').read_text().split('int main(')[0]
    source=harness.replace('/* SINGLE_BIT_EVALUATOR */',original[start:end])+MAIN
    cases={}
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp);(folder/'replay.c').write_text(source)
        subprocess.run(['cc','-std=gnu11','-O2',str(folder/'replay.c'),'-lm','-o',str(folder/'replay')],check=True)
        for name in ('25','12.5','6.25'):
            path=runs/('nested-local-full-'+name)/'network_witness.txt'
            digest=sha(path)
            endpoint=json.loads((evidence/name/'trace-endpoints.json').read_text())['network_witness.txt']
            if digest!=endpoint['sha256']:raise ValueError('Changed capture')
            run=json.loads((evidence/name/'run.json').read_text())
            column=run['observationSignals'].index('v(wr_high)')+1
            samples=[]
            for row in rows(path,run['observationSignals'],run['stepNs']):
                if row[0]>12e-9:break
                samples.append((row[0],row[column]))
            output=subprocess.check_output([str(folder/'replay'),'1e-8'],input=''.join(f'{t:.17g}\n' for t,v in samples),text=True)
            replay=list(map(float,output.splitlines()))
            if len(samples)!=len(replay):raise ValueError('Incomplete evaluator replay')
            errors=[]
            for (t,observed),value in zip(samples,replay):
                with localcontext() as c:
                    c.prec=64
                    errors.append({'timeSeconds':t,'capturedVolts':observed,'replayedVolts':value,
                        'captureMinusReplayVolts':str(D.from_float(observed)-D.from_float(value)),
                        'captureMinusExactRampVolts':str(D.from_float(observed)-exact_ramp(t)),
                        'replayMinusExactRampVolts':str(D.from_float(value)-exact_ramp(t))})
            maxima={key:max(errors,key=lambda e:abs(D(e[key]))) for key in
                    ('captureMinusReplayVolts','captureMinusExactRampVolts','replayMinusExactRampVolts')}
            if sha(path)!=digest:raise ValueError('Capture changed during review')
            origin_trials=[]
            for origin in (math.nextafter(1e-8,-math.inf),1e-8,math.nextafter(1e-8,math.inf)):
                replay_trial=list(map(float,subprocess.check_output([str(folder/'replay'),format(origin,'.17g')],
                    input=''.join(f'{t:.17g}\n' for t,v in samples),text=True).splitlines()))
                if len(replay_trial)!=len(samples):raise ValueError('Incomplete origin trial')
                origin_trials.append({'originSeconds':origin,'offsetFromNominalSeconds':origin-1e-8,
                    'allCapturedValuesMatchReplay':all(a[1]==b for a,b in zip(samples,replay_trial)),
                    'maximumCaptureDifferenceVolts':max(abs(a[1]-b) for a,b in zip(samples,replay_trial))})
            cases[name]={'captureSha256':digest,'samples':len(samples),'endSeconds':samples[-1][0],
                         'allCapturedValuesMatchReplay':all(a[1]==b for a,b in zip(samples,replay)),
                         'maxima':maxima,'originTrials':origin_trials}
    return {'schema':1,'cases':cases,'qualified':False,
        'sources':{name:sha(HERE/name) for name in ('dac_partition_review.py','fixtures/dac_ramp_harness.c','fixtures/ngspice-47/dac_bridge.mod','host_waveform_comparison.py','trace_io.py')},
        'compiledHarnessSha256':hashlib.sha256(source.encode()).hexdigest(),
        'compiler':subprocess.check_output(['cc','--version'],text=True).splitlines()[0],
        'scope':'Original pinned single-bit evaluator replay on accepted startup time partitions only, using the observed zero-to-one event at binary64 10 ns and configured 5 V/ns rising slope. Exact-ramp subtraction uses 64-digit arithmetic and the same binary64 time origin. No solver or waveform correction, time alignment, acceptance allowance or complete rollback qualification. The replay does not include rejected solver calls. Adjacent binary64 event-origin trials are diagnostic hypotheses only, not waveform alignment or proof of the actual event timestamp.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runs',type=Path,required=True);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=build(a.runs,a.evidence);a.out.write_text(json.dumps(result,indent=2)+'\n')
    for name,c in result['cases'].items():print(name,c['allCapturedValuesMatchReplay'],{k:v[k] for k,v in c['maxima'].items()})
