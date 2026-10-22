#!/usr/bin/env python3
"""Independent bus waveform checks and machine-cycle arbitration phase sweep.

Zilog UM008011-0816 figures 5, 6, 8. This is an HDL reference acceptance
fixture, not a claim that the C CPU implements arbitration or these waveforms.
"""
import argparse
import json
import subprocess
from pathlib import Path
from cpu_bus_candidate import generate
from qualify import ROOT, sha
HERE = Path(__file__).resolve().parent
FIELDS = 'cycle edge address data m1 mreq iorq rd wr rfsh halt busack address_oe data_oe control_oe wait busrq mc ts pc'.split()


def parse(log):
    result = []
    for line in log.splitlines():
        if line.startswith('PIN '):
            values = line.split()[1:]
            if len(values) != len(FIELDS):
                raise ValueError('Wrong pin capture width')
            # dout is undefined during non-writes in uninitialized register tests.
            result.append(dict(zip(FIELDS, [None if x in ('x', 'z') else int(x) for x in values])))
    if len(result) != 800 or [(r['cycle'], r['edge']) for r in result] != [(c, e) for c in range(400) for e in range(2)]:
        raise ValueError('Missing, duplicate or shifted pin observations')
    return result


def failures(rows):
    errors = []
    for r in rows:
        if r['busack']:
            if any(r[k] for k in ('address_oe', 'data_oe', 'control_oe', 'mreq', 'iorq', 'rd', 'wr', 'rfsh')):
                errors.append({'kind': 'bus-not-released', 'row': r})
        if r['rfsh'] and (r['rd'] or r['wr'] or r['iorq']):
            errors.append({'kind': 'refresh-conflict', 'row': r})
    # During a sustained grant the CPU must freeze, including register/PC work.
    for before, after in zip(rows, rows[1:]):
        if before['busack'] and after['busack'] and before['busrq'] and after['busrq']:
            if any(before[k] != after[k] for k in ('mc', 'ts', 'pc', 'address')):
                errors.append({'kind': 'cpu-advanced-during-grant', 'before': before, 'after': after})
    return errors


def nop_oracle(rows):
    errors = []
    # Independent four-clock opcode fetch, not reconstructed from TV80 states.
    for r in rows[:64]:
        t = r['cycle'] % 4
        e = r['edge']
        expected = {'m1': int(t < 2), 'rd': int((t == 0 and e == 1) or t == 1),
                    'rfsh': int(t >= 2), 'iorq': 0, 'wr': 0,
                    'mreq': int((t == 0 and e == 1) or t == 1 or (t == 2 and e == 1) or (t == 3 and e == 0)),
                    'address': r['cycle'] // 4}
        for k, v in expected.items():
            if r[k] != v:
                errors.append({'cycle': r['cycle'], 'edge': e, 'signal': k, 'expected': v, 'actual': r[k]})
    return errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-cpu-bus')
    a = ap.parse_args(); out = a.out.resolve(); rtl = generate(out / 'rtl')
    def run(cmd):
        return subprocess.check_output(list(map(str, cmd)), text=True, timeout=30)
    run(['iverilog', '-g2012', '-DTV80_REFRESH', '-s', 'probe', '-o', out / 'probe.vvp', *rtl, HERE / 'cpu_bus_probe.v'])
    results = []
    programs = {'nop': bytes(256), 'mixed': bytes.fromhex(
        '31 00 f0 21 00 80 36 5a 7e 32 01 80 01 03 80 ed 78 ed 79 dd 21 00 80 dd 7e 00 f5 f1 76'),
                'indexed': bytes.fromhex('31 00 f0 dd 21 00 80 dd 36 00 5a dd 7e 00 32 01 80 dd cb 00 06 dd 7e 00 32 02 80 76'),
                'block': bytes.fromhex('31 00 f0 21 00 80 36 5a 11 01 80 01 02 00 ed b0 01 00 03 21 00 80 ed b3 76'),
                'late': bytes.fromhex('3a 00 80 d3 00 76')}
    for name, program in programs.items():
        path = out / (name + '.hex'); path.write_text('\n'.join(f'{x:02x}' for x in program) + '\n')
        specs = [(None, None)] + ([(start, start + 17) for start in range(200)] if name != 'late' else [])
        for start, end in specs:
            args = [] if start is None else [f'+request={start}', f'+release={end}']
            if name == 'late': args += ['+late=1']
            log = run(['vvp', out / 'probe.vvp', '+rom=' + str(path), *args])
            label = name + ('-plain' if start is None else '-bus-' + str(start))
            (out / (label + '.txt')).write_text(log)
            rows = parse(log); errors = failures(rows)
            if name == 'nop' and start is None: errors += nop_oracle(rows)
            if start is not None:
                grants = [r for r in rows if r['busack']]
                if not grants or grants[-1]['cycle'] >= end + 3 or grants[0]['cycle'] > start + 8:
                    errors.append({'kind': 'missing-or-unbounded-grant'})
                if name == 'nop':
                    # Request sampled at T4 rising; acknowledge on next T1 rising.
                    first = ((start + 3) // 4) * 4
                    if first == start: first += 4
                    if not grants or grants[0]['cycle'] != first:
                        errors.append({'kind': 'grant-boundary', 'expected': first,
                                       'actual': grants[0]['cycle'] if grants else None})
            if name == 'late' and 'OUTPUT 1 52' not in log:
                errors.append({'kind': 'late-memory-data-not-sampled'})
            expected = {'mixed':'RESULT 90 90 0', 'indexed':'RESULT 180 90 180', 'block':'RESULT 90 90 90'}
            if name in expected and expected[name] not in log:
                errors.append({'kind': 'resume-state-or-memory-corrupt'})
            results.append({'id': label, 'passed': not errors, 'errors': errors})
    # WAIT spanning a memory cycle must defer a grant until that cycle finishes.
    for start in range(1, 5):
        log = run(['vvp', out / 'probe.vvp', '+rom=' + str(out / 'nop.hex'),
                   f'+request={start}', '+release=25', '+wait=1', '+wait_end=12'])
        label = f'wait-bus-{start}'; (out / (label + '.txt')).write_text(log)
        rows = parse(log); errors = failures(rows)
        grants = [r for r in rows if r['busack']]
        if not grants or grants[0]['cycle'] != 15:
            errors.append({'kind': 'grant-did-not-follow-waited-machine-cycle'})
        if not any(r['rfsh'] and r['mreq'] for r in rows if r['cycle'] > 26):
            errors.append({'kind': 'refresh-did-not-resume'})
        results.append({'id': label, 'passed': not errors, 'errors': errors})
    # IRQ IM0/1/2 and NMI delivered while the bus is held must execute after
    # release. Memory markers detect missing/duplicated ISR execution.
    for im, opcode in enumerate((0x46, 0x56, 0x5e)):
        mem = bytearray(65536)
        program = bytes.fromhex('31 00 f0 21 00 80 36 5a 3e 81 ed 47') + bytes((0xed, opcode, 0xfb, 0x76, 0x32, 0x01, 0x80, 0x76))
        mem[:len(program)] = program
        mem[0x81ff:0x8201] = bytes((0x38, 0))
        for kind in ('irq', 'nmi'):
            address = 0x38 if kind == 'irq' else 0x66
            handler = bytes.fromhex('3e 6d 32 02 80 ed') + bytes((0x4d if kind == 'irq' else 0x45,))
            mem[address:address + len(handler)] = handler
            path = out / f'{kind}-{im}.hex'
            path.write_text('\n'.join(f'{x:02x}' for x in mem) + '\n')
            for grant in (False, True):
                args = ['+request=190', '+release=215'] if grant else []
                log = run(['vvp', out / 'probe.vvp', '+rom=' + str(path), f'+{kind}=200', *args])
                label = f'{kind}-{im}-' + ('bus' if grant else 'plain')
                (out / (label + '.txt')).write_text(log)
                rows = parse(log); errors = failures(rows)
                if 'RESULT 90 109 109' not in log:
                    errors.append({'kind': 'interrupt-resume-memory-result'})
                if grant and any(r['m1'] and r['iorq'] and r['busack'] for r in rows):
                    errors.append({'kind': 'interrupt-ack-during-grant'})
                results.append({'id': label, 'passed': not errors, 'errors': errors})
    sources = [Path(__file__), HERE / 'cpu_bus_candidate.py', HERE / 'cpu_bus_candidate.v', HERE / 'cpu_bus_probe.v']
    report = {'passed': all(r['passed'] for r in results), 'productionChanged': False,
              'qualified': False, 'reference': 'https://www.zilog.com/docs/z80/um0080.pdf',
              'boundary': 'HDL fetch/refresh and bus-grant reference. C arbitration, full memory/interrupt pin agreement and production adoption remain open.',
              'cases': results, 'sources': {str(p.relative_to(ROOT)): sha(p) for p in sources},
              'artifacts': {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.suffix in ('.v', '.txt', '.hex')}}
    (out / 'assessment.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'failures': [r for r in results if not r['passed']][:3]}, indent=2))
    if not report['passed']: raise SystemExit(1)

if __name__ == '__main__': main()
