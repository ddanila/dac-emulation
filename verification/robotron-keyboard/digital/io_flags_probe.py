#!/usr/bin/env python3
"""Execute independent normal-completion I/O flag vectors on C and both HDLs."""
import argparse
import json
import random
import subprocess
from pathlib import Path
from qualify import ROOT, sha
from c_read_candidate import generate as c_generate
from io_flags_candidate import generate
from c_read_instructions import parse

HERE = Path(__file__).resolve().parent
REFERENCE = 'https://datasheets.chipdb.org/Zilog/Z80/z80-documented-0.90.pdf'


def parity(value):
    return 4 if bin(value & 255).count('1') % 2 == 0 else 0


def expected(op, data, b, c, l, initial):
    if op == 0xdb:
        return initial
    if op & 0xc7 == 0x40:
        return (data & 0xa8) | (64 if data == 0 else 0) | parity(data) | (initial & 1)
    count = 0 if op & 0x10 else (b - 1) & 255
    delta = -1 if op & 8 else 1
    term = ((l + delta * (b if op & 0x10 else 1)) if op & 1 else c + delta) & 255
    total = data + term
    return ((count & 0xa8) | (64 if count == 0 else 0) |
            (17 if total > 255 else 0) | ((data >> 6) & 2) |
            parity((total & 7) ^ count))


def vectors():
    rng = random.Random(1715)
    for op in [0xdb, *range(0x40, 0x79, 8), 0xa2, 0xaa, 0xb2, 0xba, 0xa3, 0xab, 0xb3, 0xbb]:
        # Extremes, flag-bit boundaries, carry-wrap boundaries, then seeded coverage.
        for i, data in enumerate([0, 1, 7, 8, 0x20, 0x34, 0x7f, 0x80, 0xff] + [rng.randrange(256) for _ in range(7)]):
            b = [1, 2, 3][i % 3] if op & 0x10 and op >= 0xa0 else [0, 1, 2, 0x80, 0xff][i % 5]
            yield op, data, b, [0, 1, 0x7f, 0xfe, 0xff][i % 5], [0, 1, 0x7f, 0xfe, 0xff][(i + 2) % 5], [0, 0xff][i % 2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, default=ROOT/'build/keyboard-controller-io-flags')
    ap.add_argument('--quick', action='store_true', help='CI witnesses; full retained sweep remains separate')
    args = ap.parse_args()
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    def run(cmd, log=None):
        if log:
            with log.open('w') as f:
                subprocess.run(list(map(str, cmd)), stdout=f, check=True, timeout=30)
        else:
            subprocess.run(list(map(str, cmd)), check=True, timeout=30)
    (out/'candidate.h').write_text(c_generate((ROOT/'third_party/cpu/chips/z80.h').read_text()))
    c = (HERE/'c_read_instructions.c').read_text().replace('argc!=5', 'argc!=6')
    c = c.replace(' z80_t cpu;', ' unsigned value=(unsigned)atoi(argv[5]);for(unsigned j=0x7000;j<0x9000;j++)memory[j]=value;\n z80_t cpu;')
    c = c.replace('((address^(address>>8)^0x5a)&255)', 'value')
    (out/'probe.c').write_text(c)
    run(['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-I', out, out/'probe.c', '-o', out/'probe'])
    h = (HERE/'c_read_instructions.v').read_text()
    h = h.replace('integer mode,reset_mode,i;', 'integer mode,reset_mode,i,value;')
    h = h.replace('(address[7:0]^address[15:8]^8\'h5a)', 'value[7:0]')
    h = h.replace('  $readmemh(file,memory);', '''  if (!$value$plusargs("value=%d",value)) $fatal(1,"value missing");
  for(i=28672;i<36864;i=i+1)memory[i]=value;
  $readmemh(file,memory);''')
    (out/'probe.v').write_text(h)
    vendor = ROOT/'third_party/cpu/tv80'
    (out/'tv80_core.v').write_text(generate((vendor/'tv80_core.v').read_text()))
    sources = sorted(vendor.glob('*.v'))
    for name in ('original', 'candidate'):
        rtl = sources if name == 'original' else [p for p in sources if p.name != 'tv80_core.v'] + [out/'tv80_core.v']
        run(['iverilog', '-g2012', '-s', 'c_read_instructions', '-o', out/(name+'.vvp'), *rtl, HERE/'tv80_io_candidate.v', out/'probe.v'])
    results = []
    for index, (op, data, b, c, l, initial) in enumerate(vectors()):
        if args.quick and index % 16 not in (0,8): continue
        folder = out/str(index); folder.mkdir(exist_ok=True)
        # POP AF installs deliberately opposite incoming flags without relying on ALU flags.
        program = bytes([0x31,0,0xf0,0x21,initial,0x5a,0xe5,0xf1,0x01,c,b,0x21,l,0x80])
        program += bytes([0xdb,0x80] if op == 0xdb else [0xed,op]) + b'\x76'
        (folder/'program.bin').write_bytes(program)
        (folder/'program.hex').write_text('\n'.join(f'{x:02x}' for x in program)+'\n')
        run([out/'probe',folder/'program.bin',0,0,0,data], folder/'c.txt')
        for name in ('original', 'candidate'):
            run(['vvp',out/(name+'.vvp'),'+rom='+str(folder/'program.hex'),'+mode=0','+reset=0',f'+value={data}'],folder/(name+'.txt'))
        cr = parse(folder/'c.txt'); old = parse(folder/'original.txt'); new = parse(folder/'candidate.txt')
        target = expected(op,data,b,c,l,initial)
        row = dict(id=index, opcode=op, data=data, b=b, registerC=c, l=l, initialFlags=initial, expected=target,
                   c=cr['FINAL'][-1][1], original=old['AF'][-1][1], candidate=new['AF'][-1][1],
                   halted=cr['FINAL'][-1][-1] == 1 and old['HALT'] == new['HALT'] == [[1]],
                   dataUnchanged=old['RAM']==new['RAM'] and old['OUT']==new['OUT'])
        results.append(row)
    report = {'quick':args.quick, 'reference':REFERENCE, 'sections':['4.3', '8.11'], 'scope':'Normal completion only; interrupted repeats and U880-specific undocumented behavior remain unqualified.',
              'cPass':all(r['c']==r['expected'] and r['halted'] for r in results),
              'candidatePass':all(r['candidate']==r['expected'] and r['halted'] and r['dataUnchanged'] for r in results),
              'originalDisagreements':sum(r['original']!=r['expected'] for r in results), 'cases':results,
              'sources':{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),HERE/'io_flags_candidate.py',HERE/'c_read_instructions.c',HERE/'c_read_instructions.v',HERE/'c_read_candidate.py',HERE/'tv80_io_candidate.v',ROOT/'third_party/cpu/chips/z80.h',*sources]},
              'artifacts':{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.suffix in ('.txt','.hex','.bin','.v','.c','.h')}}
    (out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
    print({k:v for k,v in report.items() if k.endswith('Pass') or k=='originalDisagreements'})
    for r in results:
        if r['candidate']!=r['expected'] or r['c']!=r['expected'] or not r['halted'] or not r['dataUnchanged']:print(r)
    if not report['cPass'] or not report['candidatePass'] or not report['originalDisagreements']:raise SystemExit(1)

if __name__ == '__main__':
    main()
