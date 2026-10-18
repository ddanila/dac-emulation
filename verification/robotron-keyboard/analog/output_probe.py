#!/usr/bin/env python3
"""Test nominal serial/cable and LED loads generated from reference connectivity."""
import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

from circuit import load
from output_circuit import output_circuit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def run(args, components, step_ns, cable_pf):
    out = args.out.resolve() / f'{step_ns}ns-{cable_pf}pf'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'trace.txt').unlink(missing_ok=True)
    lines, metadata = output_circuit(components, cable_pf, args.choke_uh, args.choke_ohms,
                                     coupling=args.coupling, dots=args.dot_pins)
    gnd = metadata['hostGround']
    lines = ['Robotron electrical output fixture; nominal external loads',
             f'Vhost {metadata["hostSupply"]} {gnd} 5', *lines,
             'Vdata data_intent 0 PWL(0 0 10u 0 10.01u 5 20u 5 20.01u 0 40u 0)',
             'Vclock clock_intent 0 PWL(0 0 12u 0 12.01u 5 22u 5 22.01u 0 40u 0)',
             'Vsiso siso_intent 0 PWL(0 0 5u 0 5.01u 5 25u 5 25.01u 0 40u 0)',
             'Vcaps caps_intent 0 PWL(0 0 7u 0 7.01u 5 27u 5 27.01u 0 40u 0)']
    signals = [f'v({metadata["serial"][label]["cable"]},{gnd})' for label in ('data', 'clock')]
    # Include rail/return drops and LED currents, not just ideal control voltages.
    signals += ['v(n_p5V)', f'v({gnd})', '@dsiso_led[id]', '@dcaps_led[id]']
    lines += ['.save ' + ' '.join(signals), '.control', 'set wr_singlescale', 'set wr_vecnames',
              f'tran {step_ns}n 40u', 'wrdata trace.txt ' + ' '.join(signals), 'quit', '.endc', '.end']
    (out / 'outputs.cir').write_text('\n'.join(lines) + '\n')
    proc = subprocess.run([args.ngspice, '-n', '-b', 'outputs.cir'], cwd=out, capture_output=True, text=True, timeout=60)
    log = proc.stdout + proc.stderr
    (out / 'ngspice.log').write_text(log)
    proc.check_returncode()
    if re.search(r'warning|error|failed|singular', log, re.I):
        raise ValueError('Solver diagnostics: ' + str(out / 'ngspice.log'))
    rows = [[float(x) for x in line.split()] for line in (out / 'trace.txt').read_text().splitlines()[1:]]
    if not rows or any(len(row) != 7 or not all(map(math.isfinite, row)) for row in rows):
        raise ValueError('Invalid electrical output trace')
    if rows[0][0] > 1e-9 or rows[-1][0] < 40e-6:
        raise ValueError('Incomplete output transient')
    samples = [min(rows, key=lambda row: abs(row[0]-t)) for t in (2e-6, 16e-6, 36e-6)]
    for index, row in enumerate(samples):
        active = index == 1
        for voltage in row[1:3]:
            if not (voltage < .8 if active else voltage > 2):
                raise ValueError('Serial drive/release failed at cable receiver')
        for current in row[5:7]:
            if not (current > .001 if active else abs(current) < .0001):
                raise ValueError('LED current failed on/off check')
    rises = []
    for column, start in [(1, 20e-6), (2, 22e-6)]:
        crossings = []
        for level in (.8, 2):
            found = [a[0] + (level-a[column])*(b[0]-a[0])/(b[column]-a[column])
                     for a, b in zip(rows, rows[1:]) if start <= a[0] < start+8e-6 and a[column] < level <= b[column]]
            if len(found) != 1:
                raise ValueError('Expected one clean receiver-threshold crossing on release')
            crossings.append(found[0])
        rises.append(crossings[1]-crossings[0])
    return {'stepNs': step_ns, 'cablePf': cable_pf, 'signals': signals,
            'samples': samples, 'receiverRiseSeconds08to2V': rises,
            'signalRanges': [[min(row[i] for row in rows), max(row[i] for row in rows)] for i in range(1, 7)],
            'deckSha256': hashlib.sha256((out / 'outputs.cir').read_bytes()).hexdigest(),
            'artifacts': {name: hashlib.sha256((out / name).read_bytes()).hexdigest()
                          for name in ('outputs.cir', 'trace.txt', 'ngspice.log')}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ngspice', default='ngspice')
    p.add_argument('--cable-pf', type=float, default=1000)
    p.add_argument('--choke-uh', type=float, default=1)
    p.add_argument('--choke-ohms', type=float, default=1)
    p.add_argument('--coupling', type=float, default=0, help='Uniform winding coupling hypothesis, 0 <= k < 1')
    p.add_argument('--dot-pins', type=int, nargs=4, choices=(1, 2), default=(1, 1, 1, 1),
                   help='Assumed dot terminal for L1.1, L1.2, L1.3, L1.4')
    p.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-analog/outputs')
    args = p.parse_args()
    if any(not math.isfinite(x) or x <= 0 for x in (args.cable_pf, args.choke_uh, args.choke_ohms)):
        p.error('load and choke parameters must be positive and finite')
    if not math.isfinite(args.coupling) or not 0 <= args.coupling < 1:
        p.error('coupling must be finite and in [0, 1)')
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / 'report.json'
    path.unlink(missing_ok=True)
    report = {'passed': False, 'qualified': False, 'scope': __doc__, 'runs': [],
              'acceptanceBoundary': 'Fixture steady-state levels, release crossings, timestep and load sensitivity only; not absolute voltage limits or calibrated full-board behavior',
              'sources': {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                          for name in ('output_probe.py', 'output_circuit.py', 'circuit.py')},
              'assumptions': {'cablePf': args.cable_pf, 'chokeUh': args.choke_uh,
                              'chokeOhms': args.choke_ohms, 'receiverOhms': 100000,
                              'serialSinkOhms': 20, 'releasedOhms': 1e12,
                              'led': 'Generic diode IS=1e-20 N=2 RS=2, not a characterized VQA33',
                              'ledOutput': '30 ohms, targets 0.04/0.70 of local supply; not characterized DL074',
                              'filter': 'Linear equal-winding RL hypothesis; coupling and ferrite behavior unqualified',
                              'coupling': args.coupling, 'dotPins': args.dot_pins,
                              'supply': 'Ideal host 5 V through supply/return chokes; controller IC quiescent currents omitted',
                              'decoupling': 'Ideal schematic capacitors; ESR/leakage omitted',
                              'stimulus': 'Ideal drive intents; separate from HDL/firmware qualification'}}
    try:
        components, report['connectivitySha256'] = load()
        _, report['circuit'] = output_circuit(components, args.cable_pf, args.choke_uh, args.choke_ohms,
                                     coupling=args.coupling, dots=args.dot_pins)
        executable = Path(shutil.which(args.ngspice) or args.ngspice).resolve()
        report['executableSha256'] = hashlib.sha256(executable.read_bytes()).hexdigest()
        report['tool'] = subprocess.check_output([args.ngspice, '--version'], text=True).strip()
        for cable_pf in (args.cable_pf, 2*args.cable_pf):
            pair = []
            for step in (10, 5):
                result = run(args, components, step, cable_pf)
                pair.append(result)
                report['runs'].append(result)
            for first, second in zip(pair[0]['receiverRiseSeconds08to2V'], pair[1]['receiverRiseSeconds08to2V']):
                if abs(first/second-1) > .01:
                    raise ValueError('Receiver rise interval fails 1% timestep refinement check')
        for first, doubled in zip(report['runs'][1]['receiverRiseSeconds08to2V'], report['runs'][3]['receiverRiseSeconds08to2V']):
            if doubled < first*1.5:
                raise ValueError('Doubling cable load did not meaningfully slow receiver rise')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        path.write_text(json.dumps(report, indent=2) + '\n')
    print(path)


if __name__ == '__main__':
    main()
