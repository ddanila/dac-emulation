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
    ap.add_argument('--pins', action='store_true')
    ap.add_argument('--require-pass', action='store_true')
    a = ap.parse_args(); folder = a.run.resolve(); out = folder/('c-pins' if a.pins else 'c'); generate(out)
    def run(cmd): return subprocess.check_output(list(map(str, cmd)), text=True, timeout=30)
    source=HERE/'cpu_bus_probe.c'
    if a.pins:
        code=source.read_text().replace('<cpu_bus_half.h>','<cpu_bus_pins.h>').replace('cpu_bus_half cpu','cpu_bus_pins cpu')
        for old,new in [('cpu_bus_reset','cpu_pins_reset'),('cpu_bus_rise','cpu_pins_rise'),('cpu_bus_fall','cpu_pins_fall'),('cpu.busack','cpu.core.busack'),('cpu.core.cpu.step','cpu.core.core.cpu.step')]: code=code.replace(old,new)
        code=code.replace('   old_write=!!(p&Z80_WR);', '   old_write=!!(p&Z80_WR);\n   printf("WIRE %d %d %u %u %d %d %d %d %d %d %d %d\\n",c,edge,Z80_GET_ADDR(p),Z80_GET_DATA(p),!!(p&Z80_M1),!!(p&Z80_MREQ),!!(p&Z80_IORQ),!!(p&Z80_RD),!!(p&Z80_WR),!!(p&Z80_RFSH),!!(p&Z80_HALT),cpu.core.busack);')
        source=out/'probe.c';source.write_text(code)
    run(['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-I', out, '-I', HERE, source, '-o', out/'probe'])
    review = json.loads((folder/'assessment.json').read_text())
    if not review['passed']: raise ValueError('HDL reference did not pass')
    results = []
    for case in review['cases']:
        label = case['id']; start = end = wait = wait_end = irq = nmi = 999
        if label.startswith(('nop-', 'mixed-', 'indexed-', 'block-', 'internal-', 'late-')):
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
        wire_errors=[]
        if a.pins:
            wires=[list(map(int,line.split()[1:])) for line in log.splitlines() if line.startswith('WIRE ')]
            keys='cycle edge address data m1 mreq iorq rd wr rfsh halt busack'.split()
            if len(wires)!=len(hr):raise ValueError('Incomplete C pin capture')
            for w,h in zip(wires,hr):
                c=dict(zip(keys,w))
                selected=[k for k in keys if k not in ('address','data')]
                if h['mreq'] or h['iorq'] or c['mreq'] or c['iorq']:selected+=['address']
                if h['wr'] or c['wr']:selected+=['data']
                diff={k:[c[k],h[k]] for k in selected if c[k]!=h[k]}
                if diff:wire_errors.append({'cycle':h['cycle'],'edge':h['edge'],'signals':diff})
        results.append({'pinMismatches':wire_errors,'id':label,'busackAgrees':not mismatches,'resultAgrees':result(log)==result(hlog),
                        'mismatches':mismatches,'cResult':result(log),'hdlResult':result(hlog)})
    report={'passed':all(r['busackAgrees'] and r['resultAgrees'] and not r['pinMismatches'] for r in results),'qualified':False,
            'cases':results,'sources':{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),HERE/'cpu_bus_c.py',HERE/'cpu_bus_half.h',HERE/'cpu_bus_pins.h',HERE/'cpu_bus_probe.c',*[HERE/name for name in ('io_repeat_candidate.py','io_complete_candidate.py','io_wait_candidate.py','io_flags_candidate.py','c_read_candidate.py','c_read_half.h')],ROOT/'third_party/cpu/chips/z80.h']},
            'pinsCompared':a.pins,'artifacts':{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.suffix in ('.h','.c','.txt','.bin')},
            'boundary':'Same labelled edges, control signals, selected addresses, write data and bus acknowledgement for the declared programs. Input data and undriven bus values are not compared as CPU outputs.'}
    (folder/('cross-pins.json' if a.pins else 'cross.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':report['passed'],'failedCases':[r['id'] for r in results if not(r['busackAgrees'] and r['resultAgrees'] and not r['pinMismatches'])]},indent=2))
    if a.require_pass and not report['passed']: raise SystemExit(1)

if __name__=='__main__': main()
