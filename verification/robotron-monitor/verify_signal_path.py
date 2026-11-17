#!/usr/bin/env python3
"""Numerical qualification of signal-path characterizations, not monitor diagnosis."""
import argparse,json,math,subprocess
from pathlib import Path
import signal_path


def compare(a,b):
    failures=[]
    for probe,metrics in a['metrics'].items():
        for name,value in metrics.items():
            other=b['metrics'][probe][name]
            if value is None or other is None:
                if value!=other:failures.append([probe,name,'feature appeared/disappeared'])
                continue
            floor=1e-10 if name.endswith('_s') else .001
            tolerance=0 if name.endswith('_edges') else max(floor,.01*abs(other))
            if not math.isfinite(value) or abs(value-other)>tolerance:
                failures.append([probe,name,value,other,tolerance])
    return dict(passed=not failures,failures=failures,relative_tolerance=.01,
                voltage_floor_v=.001,time_floor_s=1e-10,edge_count_tolerance=0)


def run(capture,output,cases=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    result=dict(format='dac-monitor-signal-verification-v1',status='incomplete',cases={},
                full_monitor_qualified=False,scope='Numerical convergence only; no real-monitor fault validation')
    save=lambda:(output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    save()
    for case in cases or signal_path.CASES:
        print(case,flush=True)
        try:
            runs={tag:signal_path.run(capture,output/case/tag,case=case,duration=60e-6,step=step,sections=sections)
                  for tag,step,sections in [('base',5e-10,4),('refined',2.5e-10,4),('cable',5e-10,8)]}
            timing=compare(runs['base'],runs['refined']);cable=compare(runs['base'],runs['cable'])
            passed=timing['passed'] and cable['passed']
            result['cases'][case]=dict(status='accepted-characterization' if passed else 'withheld',
                                      timestep=timing,cable=cable,hashes=runs['base']['hashes'])
        except (ValueError,OSError,subprocess.SubprocessError) as error:
            result['cases'][case]=dict(status='withheld',failure=str(error))
        save()
    nominal=result['cases'].get('nominal',{}).get('status')=='accepted-characterization'
    result.update(status='complete',nominal_accepted=nominal,
                  publishable_cases=[k for k,v in result['cases'].items() if nominal and v['status']=='accepted-characterization'])
    save();return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--case',choices=signal_path.CASES,action='append')
    a=p.parse_args();r=run(a.capture,a.output,a.case)
    print('accepted:',', '.join(r['publishable_cases']))
    raise SystemExit(0 if len(r['publishable_cases'])==len(r['cases']) else 1)
