"""Independent-solver oscillator diagnostic from canonical wiring and gate equations."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess

from circuit import load, node
from oscillator_probe import wiring
from clock_convergence import compare_clocks
from oscillator_supply_replay import supply_samples, check_supply

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def model_for_xyce(text):
    def convert(match):
        expression = re.sub(r'\{([A-Za-z_][A-Za-z0-9_]*)\}', r'\1', match[2])
        if '{' in expression or '}' in expression:
            raise ValueError('Unreviewed nested expression')
        return match[1] + '{' + expression + '}'
    result, count = re.subn(r'^(B\S+ \S+ \S+ [VI]=)(.+)$', convert, text, flags=re.M)
    if count != 5:
        raise ValueError('Unexpected gate source expressions')
    return result


def deck(components, step, duration=20e-6, recorded=False, source_mode="fasttable"):
    lines, _, _, _, cpu = wiring(components)
    supply, ground = [node(components['A7']['pins'][pin]) for pin in ('14', '7')]
    if ground != '0' or supply == cpu:
        raise ValueError('Unexpected oscillator supply boundary')
    source = (f'Bsupply {supply} {ground} V={{fasttable("../supply.txt")}}\n' if recorded
              else f'Vcc {supply} {ground} PWL(0 0 10n 5)\n')
    if source_mode not in ('fasttable', 'pwl'):
        raise ValueError('Unknown recorded-supply source mode')
    if recorded and source_mode == 'pwl':
        source = f'Vcc {supply} {ground} PWL FILE "../supply.txt"\n'
    signals = f'V({cpu})' + (f' V({supply})' if recorded else '')
    return ('Independent oscillator diagnostic\n.include model.cir\n' + source + '\n'.join(lines) +
            '\n.options timeint method=trap reltol=1e-6 abstol=1e-8\n'
            '.options nonlin reltol=1e-6 abstol=1e-8\n'
            '.options nonlin-tran reltol=1e-6 abstol=1e-8\n'
            f'.tran {step:.17g}n {duration:.17g} 0 {step:.17g}n\n'
            f'.print tran format=noindex file=xyce-trace.txt precision=17 {signals}\n.end\n')


def normalize(source, destination, duration=20e-6, recorded=False):
    rows = 0
    last = None
    ended = False
    with source.open() as src, destination.open('w') as dst:
        columns = ['TIME', 'V(N_CLK)'] + (['V(N_P5V)'] if recorded else [])
        if next(src).split() != columns:
            raise ValueError('Unexpected Xyce output columns')
        dst.write('time v(n_CLK)' + (' v(n_p5V)' if recorded else '') + '\n')
        for line in src:
            if line.strip() == 'End of Xyce(TM) Simulation':
                ended = True
                if any(x.strip() for x in src):
                    raise ValueError('Unexpected data after Xyce footer')
                break
            tokens = line.split()
            if len(tokens) != len(columns) or not all(math.isfinite(float(x)) for x in tokens):
                raise ValueError('Invalid Xyce waveform')
            time = float(tokens[0])
            if last is None and time != 0 or last is not None and time < last:
                raise ValueError('Invalid Xyce time ordering or start')
            dst.write(' '.join(tokens) + '\n')
            last = time
            rows += 1
    if not ended or last is None or abs(last - duration) > 1e-15:
        raise ValueError('Incomplete Xyce waveform')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--xyce', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--source-mode', choices=('fasttable', 'pwl'), default='fasttable')
    parser.add_argument('--source', type=Path, help='Logical uncompressed diagnostic supply trace path; compressed siblings supported')
    parser.add_argument('--steps-ns', nargs=2, type=float, default=[.25, .125])
    args = parser.parse_args()
    if not all(math.isfinite(x) and x > 0 for x in args.steps_ns) or args.steps_ns[0] <= args.steps_ns[1]:
        parser.error('Require positive coarse and smaller fine steps')
    if args.source_mode != 'fasttable' and args.source is None:
        parser.error('--source-mode pwl requires --source')
    executable = shutil.which(args.xyce)
    if not executable:
        raise ValueError('Xyce executable not found')
    executable = Path(executable).resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    runtime = {'path': str(executable), 'sha256': sha(executable),
               'version': subprocess.check_output([str(executable), '-v'], text=True).strip(),
               'capabilities': subprocess.check_output([str(executable), '-capabilities'], text=True).splitlines()}
    library = executable.parent.parent / 'lib/libxyce.dylib'
    if library.exists():
        runtime['library'] = {'path': str(library.resolve()), 'sha256': sha(library)}
    report = {'qualified': False, 'completed': False, 'runs': [], 'runtime': runtime,
              'scope': 'Isolated oscillator with nominal CPU load; no HDL or coupled power network.',
              'supplyMode': 'recorded-' + args.source_mode if args.source else 'ideal-5V-10ns',
              'boundary': 'Same gate equations and canonical connectivity, different solver. Xyce time-integration and nonlinear tolerances do not have identical semantics to ngspice tolerances. Numerical agreement is not device calibration.',
              'sources': {name: sha(HERE / name) for name in
                          ('xyce_oscillator_probe.py', 'ls_nand_pullup.cir', 'oscillator_probe.py', 'circuit.py', 'clock_convergence.py', 'oscillator_supply_replay.py', 'trace_io.py')}}
    try:
        duration = 20e-6
        if args.source:
            times, volts, report['supply'] = supply_samples(args.source, out / 'supply.txt')
            duration = times[-1]
            report['supplyBoundary'] = ('Full printed samples and linear interpolation. ' +
                ('Fasttable has only first/last table breakpoints. ' if args.source_mode == 'fasttable'
                 else 'Native PWL schedules corner breakpoints. ') +
                'Each saved supply value is checked. No live supply loading feedback or physical supply model.')
        components, report['connectivitySha256'] = load()
        model = model_for_xyce((HERE / 'ls_nand_pullup.cir').read_text())
        for label, step in zip(('coarse', 'fine'), args.steps_ns):
            run = out / label
            run.mkdir()
            (run / 'model.cir').write_text(model)
            (run / 'oscillator.cir').write_text(deck(components, step, duration, bool(args.source), args.source_mode))
            record = {'stepNs': step, 'deckSha256': sha(run / 'oscillator.cir'), 'modelSha256': sha(run / 'model.cir')}
            report['runs'].append(record)
            with (run / 'xyce.log').open('w') as log:
                result = subprocess.run([str(executable), 'oscillator.cir'], cwd=run, stdout=log,
                                        stderr=subprocess.STDOUT, timeout=600)
            record.update(exitCode=result.returncode, logSha256=sha(run / 'xyce.log'))
            result.check_returncode()
            if re.search(r'\b(?:warning|error|fatal)\b', (run / 'xyce.log').read_text(), re.I):
                raise ValueError('Xyce reports a warning or error')
            record['samples'] = normalize(run / 'xyce-trace.txt', run / 'trace.txt', duration, bool(args.source))
            if args.source:
                record['supplyCheck'] = check_supply(run / 'trace.txt', times, volts)
            record['producerTraceSha256'] = sha(run / 'xyce-trace.txt')
            record['normalizedTraceSha256'] = sha(run / 'trace.txt')
        if sha(executable) != runtime['sha256'] or library.exists() and sha(library) != runtime['library']['sha256']:
            raise ValueError('Xyce runtime changed during execution')
        report['clockPhase'] = compare_clocks(out / 'coarse/trace.txt', out / 'fine/trace.txt', *args.steps_ns, columns=3 if args.source else 2)
        report['completed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'assessment.json').write_text(json.dumps(report, indent=2) + '\n')
    return 0 if report['clockPhase']['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
