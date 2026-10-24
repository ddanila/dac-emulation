#!/usr/bin/env python3
"""Signed reset-capacitor voltage diagnostic using the retained source-variant circuits."""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess

from circuit import load, node

HERE=Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(rows):
    if (len(rows)<2 or any(len(r)!=4 or not all(map(math.isfinite,r)) for r in rows)
            or rows[0][0]!=0 or abs(rows[-1][0]-7)>1e-12
            or any(b[0]<=a[0] for a,b in zip(rows,rows[1:]))):
        raise ValueError('Incomplete or invalid signed capacitor trace')
    result={}
    for ref,column in (('C2',2),('C4',3)):
        windows={}
        for name,start,end in [('startup',0,3),('power-off',3,4),('recovery',4,7),('first-steady',2.5,2.99),('recovered-steady',6.5,7)]:
            samples=[r for r in rows if start<=r[0]<=end]
            if not samples:raise ValueError('Missing observation window')
            low=min(samples,key=lambda r:r[column]);high=max(samples,key=lambda r:r[column])
            windows[name]={'minimumVoltsPin1MinusPin2':low[column],'minimumAtSeconds':low[0],
                'maximumVoltsPin1MinusPin2':high[column],'maximumAtSeconds':high[0],
                'sampleCount':len(samples)}
        result[ref]=windows
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--ngspice',default='ngspice')
    args=parser.parse_args()
    executable=shutil.which(args.ngspice)
    if not executable:parser.error('ngspice not found')
    executable=Path(executable).resolve()
    components,connectivity=load()
    args.out.mkdir(parents=True,exist_ok=True)
    report={'completed':False,'qualified':False,'scope':__doc__,
        'connectivitySha256':connectivity,'pins':{ref:components[ref]['pins'] for ref in ('C2','C4')},
        'runtime':{'executableSha256':digest(executable),'version':subprocess.check_output([str(executable),'--version'],text=True)},
        'sources':{'reset_capacitor_polarity.py':digest(Path(__file__)),'circuit.py':digest(HERE/'circuit.py')},
        'runs':[], 'boundary':'Isolated reset with ideal R/C, ideal 5 V supply ramps and exploratory semiconductor profiles. Sampled signed voltages do not establish installed polarity, allowable reverse voltage, capacitor leakage/ESR or full-board electrical qualification.'}
    try:
        for profile in ('generic','sc236-dc'):
            baseline=HERE/'reports/reset-capacitance'/profile/'assessment.json'
            prior=json.loads(baseline.read_text())
            if prior['connectivitySha256']!=connectivity or not prior['completed']:raise ValueError('Reference baseline mismatch')
            report['sources'][str(baseline.relative_to(HERE))]=digest(baseline)
            for variant in ('zander','factory'):
                source=baseline.parent/variant/'closed-50us/reset.cir'
                original=source.read_text()
                receipt=next(r for r in prior['runs'] if r['variant']==variant and r['stepUs']==50)
                if digest(source)!=receipt['artifacts']['reset.cir']:raise ValueError('Retained circuit changed')
                report['sources'][str(source.relative_to(HERE))]=digest(source)
                signals=[]
                for ref in ('C2','C4'):
                    p1,p2=[node(components[ref]['pins'][p]) for p in ('1','2')]
                    if not re.search(r'^'+ref+' '+p1+' '+p2+r' ',original,re.M):raise ValueError('Capacitor net mapping differs')
                    signals.append(f'v({p1})' if p2=='0' else f'v({p1},{p2})')
                for step in (50,25):
                    directory=args.out/profile/variant/f'{step}us';directory.mkdir(parents=True,exist_ok=True)
                    deck=re.sub(r'^tran .*$',f'tran {step}u 7 0 {step}u',original,flags=re.M)
                    deck=re.sub(r'^wrdata .*$', 'wrdata capacitors.txt v(n_p5V) '+' '.join(signals),deck,flags=re.M)
                    (directory/'reset.cir').write_text(deck)
                    (directory/'capacitors.txt').unlink(missing_ok=True)
                    proc=subprocess.run([str(executable),'-n','-b','reset.cir'],cwd=directory,capture_output=True,text=True,timeout=60)
                    log=proc.stdout+proc.stderr;(directory/'ngspice.log').write_text(log)
                    proc.check_returncode()
                    if re.search(r'warning|error|failed|singular',log,re.I):raise ValueError('Solver diagnostics')
                    trace=directory/'capacitors.txt';raw=trace.read_bytes()
                    rows=[[float(v) for v in line.split()] for line in raw.decode().splitlines()[1:]]
                    result=summarize(rows)
                    compressed=directory/'capacitors.txt.gz';compressed.write_bytes(gzip.compress(raw,mtime=0))
                    report['runs'].append({'profile':profile,'c4Variant':variant,'stepUs':step,
                        'directory':str(directory.relative_to(args.out)),'observations':result,
                        'artifacts':{name:digest(directory/name) for name in ('reset.cir','ngspice.log','capacitors.txt','capacitors.txt.gz')}})
                    trace.unlink()
        for name,expected in report['sources'].items():
            if digest(HERE/name)!=expected:raise ValueError('Source changed: '+name)
        if digest(executable)!=report['runtime']['executableSha256']:raise ValueError('Runtime changed')
        report['completed']=True
    except Exception as error:
        report['error']=str(error)
        raise
    finally:
        (args.out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
    print(args.out/'assessment.json')


if __name__=='__main__':main()
