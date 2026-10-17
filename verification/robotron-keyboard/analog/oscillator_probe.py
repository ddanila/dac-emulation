#!/usr/bin/env python3
"""Exercise the schematic RC oscillator using an explicitly nominal LS NAND model."""
import argparse
import hashlib
import json
import math
import re
import statistics
import subprocess
from pathlib import Path

from circuit import elements, load, node
from clock_convergence import compare_clocks

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
GATES = (('1', '2', '3'), ('4', '5', '6'), ('9', '10', '8'), ('12', '13', '11'))


def wiring(components, isolated=False, capacitance_scale=1):
    gate = components['A7']
    if gate['type'] != 'DL000' or set(gate['pins']) != {str(n) for n in range(1, 15)}:
        raise ValueError('Unexpected oscillator gate package')
    lines, models = elements(components, ('R4.3', 'C6', 'R10.3'))
    # Scaling is an explicit sensitivity stimulus, never a modification to the source.
    lines = [re.sub(r'^(C6 \S+ \S+) (\S+)', rf'\1 {{\2*{capacitance_scale}}}', line) for line in lines]
    unused = []
    for index, pins in enumerate(GATES):
        nets = []
        for pin in pins:
            name = gate['pins'][pin]
            nets.append(node(name) if name else 'a7_unconnected_' + pin)
            if name is None:
                unused.append(pin)
        lines.append(f'XA7_{index} ' + ' '.join(nets + [node(gate['pins']['14']), node(gate['pins']['7'])]) + ' LS_NAND_NOMINAL')
    bridge = components['BR1']
    if bridge['type'] != 'BRIDGE' or set(bridge['pins']) != {'1', '2'}:
        raise ValueError('Unexpected BR1 topology')
    source, cpu = [node(bridge['pins'][p]) for p in ('1', '2')]
    if cpu != node(components['A5']['pins']['6']):
        raise ValueError('BR1 no longer feeds the CPU clock pin')
    lines += [f'RBR1 {source} {cpu} {"1t" if isolated else ".001"}',
              f'Rcpu {cpu} 0 1g', f'Ccpu {cpu} 0 10p']
    if isolated:
        lines.append(f'Rfixture {cpu} 0 10')
    models.update({'A7': 'LS_NAND_NOMINAL', 'BR1': '1 milliohm closed / 1 teraohm open'})
    return lines, models, unused, source, cpu


def rising_edges(rows, column, level=2):
    return [a[0] + (level-a[column]) * (b[0]-a[0]) / (b[column]-a[column])
            for a, b in zip(rows, rows[1:]) if a[0] > 5e-6 and a[column] < level <= b[column]]


def simulate(args, components, step, isolated=False, scale=1):
    out = args.out.resolve() / f'{"isolated" if isolated else "closed"}-{step}ns-c{scale}'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'trace.txt').unlink(missing_ok=True)
    model = args.gate_model.read_text()
    (out / 'ls_nand_nominal.cir').write_text(model)
    lines, models, unused, source, cpu = wiring(components, isolated, scale)
    signals = [source, cpu, 'n_OSC_RC', 'n_OSC1', 'n_OSC2']
    lines = ['Robotron reference oscillator; nominal LS-TTL model',
             'Vcc n_p5V 0 PWL(0 0 10n 5)',
             f'.options reltol={args.reltol} vntol={args.vntol} abstol={args.abstol}',
             '.include ls_nand_nominal.cir', *lines,
             '.control', 'set wr_singlescale', 'set wr_vecnames', f'tran {step}n 20u',
             'wrdata trace.txt ' + ' '.join(f'v({n})' for n in signals), 'quit', '.endc', '.end']
    deck = '\n'.join(lines) + '\n'
    (out / 'oscillator.cir').write_text(deck)
    proc = subprocess.run([args.ngspice, '-b', 'oscillator.cir'], cwd=out,
                          capture_output=True, text=True, timeout=60)
    log = proc.stdout + proc.stderr
    (out / 'ngspice.log').write_text(log)
    proc.check_returncode()
    if re.search(r'warning|error|failed|singular', log, re.I):
        raise ValueError('Solver diagnostics: ' + str(out / 'ngspice.log'))
    rows = [[float(x) for x in line.split()] for line in (out / 'trace.txt').read_text().splitlines()[1:]]
    if not rows or any(len(r) != len(signals) + 1 or not all(map(math.isfinite, r)) for r in rows):
        raise ValueError('Incomplete/invalid oscillator waveform')
    if rows[0][0] > 1e-9 or rows[-1][0] < 20e-6:
        raise ValueError('Oscillator transient endpoints missing')
    edges = rising_edges(rows, 1)
    periods = [b-a for a, b in zip(edges, edges[1:])]
    if len(periods) < 5:
        raise ValueError('Oscillator did not sustain transitions after startup')
    period = statistics.mean(periods)
    if (max(periods)-min(periods))/period > .02:
        raise ValueError('Oscillator period did not settle within 2%')
    steady = [r for r in rows if r[0] > 5e-6]
    if min(r[1] for r in steady) >= .8 or max(r[1] for r in steady) <= 2:
        raise ValueError('Clock fails TTL logic-level excursion check')
    if isolated:
        if max(abs(r[2]) for r in rows) > .1:
            raise ValueError('BR1 did not isolate the grounded clock fixture')
    elif max(abs(r[1]-r[2]) for r in rows) > .01 or len(rising_edges(rows, 2)) != len(edges):
        raise ValueError('BR1 did not carry oscillator transitions to CPU clock pin')
    return {'stepNs': step, 'br1Closed': not isolated, 'capacitanceScale': scale,
            'frequencyHz': 1/period, 'relativePeriodSpread': (max(periods)-min(periods))/period,
            'sourceRangeVolts': [min(r[1] for r in steady), max(r[1] for r in steady)],
            'models': models, 'unconnectedA7Pins': unused, 'signals': signals,
            'deckSha256': hashlib.sha256(deck.encode()).hexdigest(),
            'trace': str((out / 'trace.txt').relative_to(args.out.resolve())),
            'traceSha256': hashlib.sha256((out / 'trace.txt').read_bytes()).hexdigest()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ngspice', default='ngspice')
    p.add_argument('--gate-profile', choices=('nominal', 'dl000-dc'), default='nominal')
    p.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-analog/oscillator')
    p.add_argument('--steps-ns', type=float, nargs=2, default=(2, 1), metavar=('COARSE', 'FINE'))
    p.add_argument('--reltol', type=float, default=.001)
    p.add_argument('--vntol', type=float, default=1e-6)
    p.add_argument('--abstol', type=float, default=1e-12)
    p.add_argument('--require-phase', action='store_true', help='Require absolute edge/bracket agreement within 15 ns over the saved window')
    args = p.parse_args()
    if any(not math.isfinite(v) or v <= 0 for v in (*args.steps_ns, args.reltol, args.vntol, args.abstol)):
        p.error('Timesteps and solver tolerances must be positive and finite')
    if args.steps_ns[1] > args.steps_ns[0] / 2:
        p.error('Fine timestep must be at most half the coarse timestep')
    args.gate_model = HERE / ('ls_nand_nominal.cir' if args.gate_profile == 'nominal' else 'ls_nand_dc.cir')
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / 'report.json'
    path.unlink(missing_ok=True)
    report = {'passed': False, 'scope': __doc__, 'runs': [], 'refinements': [],
              'phaseRequired': args.require_phase, 'phaseQualified': False,
              'solver': {'reltol': args.reltol, 'vntol': args.vntol, 'abstol': args.abstol},
              'sources': {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                          for name in ('oscillator_probe.py', 'circuit.py', 'clock_convergence.py', 'trace_io.py', args.gate_model.name)},
              'assumptions': {'model': 'Continuous behavioral NAND, not transistor-level DL000 characterization',
                              'supply': 'Ideal 5 V ramp over 10 ns; gate output supply current omitted',
                              'thresholdVolts': 1.4, 'transitionWidthVolts': .1,
                              'gateProfile': args.gate_profile,
                              'internalPoleSeconds': 5e-9, 'outputOhms': {'low': 30, 'high': 50 if args.gate_profile == 'dl000-dc' else 30},
                              'outputTargetsAsSupplyFraction': {'low': .04, 'high': .70},
                              'inputFarads': 3e-12, 'cpuLoad': '1 gigaohm and 10 pF',
                              'inputBias': 'Supply-scaled 1.6 V through a one-way 10 kohm equivalent',
                              'clamp': 'Generic diode IS=1e-14, N=1, RS=20',
                              'frequency': 'Prediction of nominal model; not calibrated to emulator or measured specimen'},
              'reference': 'https://datenblatt.weithclan.de/Daten/DL000-030D-ME_ocr.pdf'}
    try:
        components, report['connectivitySha256'] = load()
        report['tool'] = subprocess.check_output([args.ngspice, '--version'], text=True).strip()
        for isolated, scale in ((False, 1), (True, 1), (False, 2)):
            pair = []
            for step in args.steps_ns:
                result = simulate(args, components, step, isolated, scale)
                pair.append(result)
                report['runs'].append(result)
            difference = abs(pair[0]['frequencyHz']/pair[1]['frequencyHz']-1)
            phase = compare_clocks(args.out / pair[0]['trace'], args.out / pair[1]['trace'],
                                   *args.steps_ns, columns=6)
            report['refinements'].append({'br1Closed': not isolated, 'capacitanceScale': scale,
                                          'relativeFrequencyDifference': difference,
                                          'clockPhase': phase})
            if args.require_phase and not phase['passed']:
                raise ValueError('Absolute oscillator phase fails timestep refinement')
            if difference > .01:
                raise ValueError('Frequency changes by more than 1% under timestep refinement')
        nominal = report['runs'][1]['frequencyHz']
        doubled = report['runs'][-1]['frequencyHz']
        if doubled >= .9*nominal:
            raise ValueError('Doubling the timing capacitor did not meaningfully lower oscillator frequency')
        report['phaseQualified'] = all(r['clockPhase']['passed'] for r in report['refinements'])
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        path.write_text(json.dumps(report, indent=2) + '\n')
    print(path)


if __name__ == '__main__':
    main()
