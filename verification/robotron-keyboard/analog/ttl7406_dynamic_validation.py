#!/usr/bin/env python3
"""Withheld DC temperature checks and undefined-input settling for a fitted candidate."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil

from gate_switching_probe import sha
from ttl7406_dynamic import model, run, switching

HERE=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--device-report',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--ngspice',default='ngspice')
    a=p.parse_args();a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=False)
    device=json.loads(a.device_report.read_text())
    if not device['completed'] or not device['cases'][0]['selectedScreensPass']:
        raise ValueError('Incomplete or failing device candidate')
    for name,digest in device['sources'].items():
        if sha(HERE/name)!=digest:raise ValueError('Stale calibration source: '+name)
    params=device['cases'][0]['parameters'];candidate=model(**params)
    executable=Path(shutil.which(a.ngspice) or a.ngspice).resolve()
    (a.out/'spinit').write_text('* Independent device validation.\n')
    env=dict(os.environ,SPICE_SCRIPTS=str(a.out))
    report=dict(completed=False,qualified=False,boardAdmission=False,
        calibrationSha256=sha(a.device_report),parameters=params,
        executableSha256=sha(executable),sourceSha256=sha(Path(__file__)),
        temperatureChecks=[],loadingRefinement=[],undefinedInput=[],
        boundary='DC limits apply over the published temperature range. Loading and undefined-input tests check numerical behavior, not undocumented device waveforms. No parameter is fitted here.')
    try:
        cases=json.loads((HERE/'ttl7406_limits.json').read_text())['cases']
        for temp in (0,70):
            for case in cases:
                rows=run(a.out/f'dc-{temp}-{case["name"]}',executable,env,candidate,f'''
* Override the common probe's nominal temperature for this withheld check.
.temp {temp}
Vcc vp 0 {case['supplyVolts']}
Vin a 0 {case['inputVolts']}
Rload vp y {case['pullupOhms']}
Iload 0 y {case['injectedOutputAmps']}
Xdut a y vp 0 TTL7406_DYNAMIC
''','op','v(a) v(y) i(Vcc) i(Vin)')
                r=rows[0];sample=dict(inputVolts=r[1],outputVolts=r[2],supplyAmps=-r[3],inputAmps=-r[4])
                value=sample[case['metric']]
                report['temperatureChecks'].append(dict(temperatureC=temp,name=case['name'],sample=sample,
                    withinLimit=case.get('minimum',-math.inf)<=value<=case.get('maximum',math.inf)))
        for cap in (15,100,1000):
            measured=[switching(a.out/f'load-{cap}-{step}',executable,env,params,step=step,load=560,cap=cap) for step in (.1,.05,.025)]
            differences=[max(abs(x[n][k]-y[n][k]) for n in ('tPHL','tPLH') for k in ('minimumNs','maximumNs')) for x,y in zip(measured,measured[1:])]
            report['loadingRefinement'].append(dict(loadOhms=560,loadPf=cap,runs=measured,
                maximumBracketDifferencesNs=differences,converged=all(d<=.2 for d in differences)))
        for target in (.8,1.4,2):
            final=[]
            for initial in (0,3):
                rows=run(a.out/f'plateau-{target}-from-{initial}',executable,env,candidate,f'''
Vcc vp 0 5
Vin generator 0 PWL(0 {initial} 200n {initial} 207n {target} 12u {target})
Rsource generator a 50
Xdut a y vp 0 TTL7406_DYNAMIC
Rload vp y 560
Cload y 0 1000p
''','tran .1n 12u 0 .1n','v(a) v(y) i(Vcc) i(Vin)')
                if rows[-1][0]<12e-6:raise ValueError('Incomplete plateau')
                final.append(dict(initialV=initial,inputV=rows[-1][1],outputV=rows[-1][2],supplyA=-rows[-1][3],inputA=-rows[-1][4]))
            difference=abs(final[0]['outputV']-final[1]['outputV'])
            report['undefinedInput'].append(dict(generatorPlateauV=target,final=final,
                holdSeconds=(12000-207)*1e-9,loadTimeConstantSeconds=560e-9,outputDifferenceV=difference,settledHistoryIndependent=difference<1e-6))
        report['completed']=True
        report['allScreensPass']=all(c['withinLimit'] for c in report['temperatureChecks']) and all(c['converged'] for c in report['loadingRefinement']) and all(c['settledHistoryIndependent'] for c in report['undefinedInput'])
        if sha(executable)!=report['executableSha256']:raise ValueError('Simulator changed')
    except Exception as error:
        report['error']=str(error);raise
    finally:
        report['artifacts']={str(f.relative_to(a.out)):sha(f) for f in sorted(a.out.rglob('*')) if f.is_file() and f.name!='report.json'}
        (a.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(a.out/'report.json')


if __name__=='__main__':main()
