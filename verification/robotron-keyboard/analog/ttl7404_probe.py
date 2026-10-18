#!/usr/bin/env python3
"""Screen a published 7404 topology against selected D104 DC conditions."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from failure_evidence import solver_diagnostic

HERE=Path(__file__).resolve().parent

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def fixtures(limits):
    cases=[]
    for check in limits['dcChecks']:
        c=dict(check)
        c['name']=c['parameter']
        c['input']=f'Vin a 0 {c["inputV"]}'
        c['output']=f'Iload y 0 {-c.get("outputCurrentA",0)}'
        cases.append(c)
    cases += [dict(name='ICCH',supplyV=5.25,input='Vin a 0 0',output='Iload y 0 0',maxA=.012/6),
              dict(name='ICCL',supplyV=5.25,input='Vin a 0 5',output='Iload y 0 0',maxA=.033/6)]
    return cases


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--ngspice',default='ngspice')
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    executable=Path(shutil.which(args.ngspice) or args.ngspice).resolve()
    (args.out/'spinit').write_text('* No external initialization.\n')
    env=dict(os.environ,SPICE_SCRIPTS=str(args.out.resolve()))
    limits=json.loads((HERE/'d104_limits.json').read_text())
    report={'completed':False,'qualified':False,'sourceTopology':{'url':'https://www.ti.com/lit/ds/symlink/sn7404.pdf','locator':"SDLS029C page 4 standard '04 schematic; not LS04 or S04"},
            'sources':{name:sha(HERE/name)for name in ('ttl7404_probe.py','ttl7404_nominal.cir','d104_limits.json','failure_evidence.py')},
            'executableSha256':sha(executable),'spinitSha256':sha(args.out/'spinit'),
            'loadConvention':'Datasheet output current is positive into DUT; the y-to-ground load source uses its negative.',
            'scope':'Selected D104 DC limits at 25 C only. TI topology applicability, switching, clamp I/V and process corners remain unqualified.', 'candidates':[]}
    try:
        for br in (1,.01):
            candidate={'inputReverseBeta':br,'checks':[],'selectedDcWithinLimits':False}
            report['candidates'].append(candidate)
            for c in fixtures(limits):
                folder=args.out/f"br{br}-{c['name']}";folder.mkdir()
                deck=['Generic 7404 DC screening',f'Vcc vp 0 {c["supplyV"]}',c['input'],c['output'],
                      f'Xgate a y vp 0 TTL7404_NOMINAL input_br={br}',
                      (HERE/'ttl7404_nominal.cir').read_text(),'.temp 25','.control',
                      'set wr_singlescale','set wr_vecnames','set numdgt=17','op',
                      'wrdata trace.txt v(a) v(y) i(Vin) i(Vcc)','quit','.endc','.end']
                (folder/'probe.cir').write_text('\n'.join(deck)+'\n')
                proc=subprocess.run([str(executable),'-n','-b','probe.cir'],cwd=folder,env=env,capture_output=True,text=True,timeout=30)
                log=proc.stdout+proc.stderr;(folder/'ngspice.log').write_text(log)
                proc.check_returncode()
                if solver_diagnostic(log):raise ValueError(solver_diagnostic(log))
                rows=(folder/'trace.txt').read_text().splitlines()[1:]
                if len(rows)!=1:raise ValueError('Incomplete DC observation')
                row=list(map(float,rows[0].split()))
                if len(row)!=5 or not all(map(math.isfinite,row)):raise ValueError('Invalid DC observation')
                va,vy,iv,icc=row[1:];ii=-iv;isupply=-icc
                name=c['name']
                if name=='IIL':value=abs(ii);passed=value<=c['maxMagnitudeA'] and ii<=0
                elif name=='IIH':value=ii;passed=0<=value<=c['maxA']
                elif name=='VOH':value=vy;passed=c['minV']<=value<=c['supplyV']
                elif name=='VOL':value=vy;passed=0<=value<=c['maxV']
                else:value=isupply;passed=0<=value<=c['maxA']
                candidate['checks'].append({'fixture':c,'inputV':va,'outputV':vy,'inputCurrentA':ii,'supplyCurrentA':isupply,'value':value,'withinLimit':passed,
                                            'artifacts':{name:sha(folder/name)for name in ('probe.cir','trace.txt','ngspice.log')}})
            candidate['selectedDcWithinLimits']=all(c['withinLimit']for c in candidate['checks'])
        if sha(executable)!=report['executableSha256']:raise ValueError('Simulator changed')
        report['completed']=True
    finally:(args.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(args.out/'report.json')

if __name__=='__main__':main()
