#!/usr/bin/env python3
"""Compare C arbitration with the independently checked HDL captures."""
import argparse
import json
import subprocess
from pathlib import Path
from cpu_bus_c import generate
from cpu_bus_review import parse
from qualify import ROOT, sha
HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', type=Path, default=ROOT/'build/keyboard-controller-cpu-bus')
    ap.add_argument('--require-pass', action='store_true')
    a = ap.parse_args(); folder = a.run.resolve(); out = folder/'c'; generate(out)
    def run(cmd): return subprocess.check_output(list(map(str, cmd)), text=True, timeout=30)
    run(['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-I', out, '-I', HERE, HERE/'cpu_bus_probe.c', '-o', out/'probe'])
    review = json.loads((folder/'assessment.json').read_text())
    if not review['passed']: raise ValueError('HDL reference did not pass')
    results = []
    for case in review['cases']:
        label = case['id']; start = end = wait = wait_end = irq = nmi = 999
        if label.startswith(('nop-', 'mixed-', 'indexed-', 'block-', 'late-')):
            program = label.split('-')[0]
            if '-bus-' in label: start=int(label.rsplit('-',1)[1]); end=start+17
        elif label.startswith('wait-bus-'):
            program='nop'; start=int(label.rsplit('-',1)[1]); end=25; wait=1; wait_end=12
        else:
            kind, im, grant = label.split('-'); program=kind+'-'+im
            if grant=='bus': start=190; end=215
            if kind=='irq': irq=200
            else: nmi=200
        binary=out/(program+'.bin')
        binary.write_bytes(bytes(int(v,16) for v in (folder/(program+'.hex')).read_text().split()))
        hlog=(folder/(label+'.txt')).read_text(); hr=parse(hlog)
        late=min(r['cycle'] for r in hr if r['address']==0x8000 and r['ts']==8 and r['rd']) if program=='late' else 999
        log=run([out/'probe',binary,start,end,wait,wait_end,irq,nmi,late])
        (out/(label+'.txt')).write_text(log)
        cr=[list(map(int,line.split()[1:])) for line in log.splitlines() if line.startswith('BUS ')]
        if len(cr)!=len(hr): raise ValueError('Incomplete C capture')
        mismatches=[{'c':c,'hdl':[h['cycle'],h['edge'],h['busack']]} for c,h in zip(cr,hr) if c[:3]!=[h['cycle'],h['edge'],h['busack']]]
        result=lambda text:[line for line in text.splitlines() if line.startswith(('RESULT ','OUTPUT '))]
        results.append({'id':label,'busackAgrees':not mismatches,'resultAgrees':result(log)==result(hlog),
                        'mismatches':mismatches,'cResult':result(log),'hdlResult':result(hlog)})
    report={'passed':all(r['busackAgrees'] and r['resultAgrees'] for r in results),'qualified':False,
            'cases':results,'sources':{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),HERE/'cpu_bus_c.py',HERE/'cpu_bus_half.h',HERE/'cpu_bus_probe.c']},
            'boundary':'C arbitration timing and functional results only. C memory/refresh/interrupt pins remain outside the qualified I/O adapter.'}
    (folder/'cross.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':report['passed'],'failedCases':[r['id'] for r in results if not(r['busackAgrees'] and r['resultAgrees'])]},indent=2))
    if a.require_pass and not report['passed']: raise SystemExit(1)

if __name__=='__main__': main()
