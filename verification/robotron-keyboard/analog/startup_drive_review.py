#!/usr/bin/env python3
"""Review bounded DAC-corner controls without claiming long-run qualification."""
import argparse,json
from pathlib import Path
from host_waveform_comparison import rows,compare_samples
from numerical_voltage_budget import voltage_gate
from network_refinement_review import normalized
from gate_switching_probe import sha


def inspect(root):
    report={'completed':True,'qualified':False,'scope':'0–100 ns startup diagnostic; no repeat traffic or production-default change.','modes':{}}
    anchor=json.loads((root/'disabled-25/run.json').read_text())
    for mode in ('disabled','corners'):
        pairs=[];inputs={}
        for a,b in [('25','12.5'),('12.5','6.25')]:
            dirs=[root/f'{mode}-{level}' for level in (a,b)]
            receipts=[json.loads((p/'run.json').read_text()) for p in dirs]
            if any(r['exitCode']!=0 or r['timedOut'] or r['solverDiagnostic'] or r['enabled']!=(mode=='corners') for r in receipts):
                raise ValueError('Incomplete or wrong startup control')
            for r in receipts:
                if any(r[key]!=anchor[key] for key in ('runtime','inputs','sourceDeckSha256')):raise ValueError('Changed disabled/enabled circuit or runtime')
            if receipts[0]['stepNs']!=2*receipts[1]['stepNs'] or receipts[0]['toleranceScale']!=2*receipts[1]['toleranceScale']:raise ValueError('Expected matched refinement')
            for key in ('runtime','inputs','sourceDeckSha256','observationSignals'):
                if receipts[0][key]!=receipts[1][key]:raise ValueError('Different '+key)
            if normalized((dirs[0]/'io.cir').read_text())!=normalized((dirs[1]/'io.cir').read_text()):raise ValueError('Changed physical circuit')
            names=receipts[0]['observationSignals']
            data=compare_samples(*(rows(p/'network_witness.txt',names,r['stepNs']) for p,r in zip(dirs,receipts)))
            if abs(data['endSeconds']-1e-7)>1e-20:raise ValueError('Incomplete startup interval')
            pairs.append({'signals':{name:{'unit':'V' if name.startswith('v(') else 'A','maximumAbsoluteDifference':v['maximumDifferenceV']} for name,v in zip(names,data['signals'])}})
            for path in dirs:
                inputs[path.name]={name:sha(path/name) for name in ('io.cir','run.json','network_witness.txt','ngspice.log')}
        report['modes'][mode]={'pairs':pairs,'voltage':voltage_gate(pairs),'inputs':inputs}
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
    a.out.write_text(json.dumps(inspect(a.root),indent=2)+'\n')
