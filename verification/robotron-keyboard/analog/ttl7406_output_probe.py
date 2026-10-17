#!/usr/bin/env python3
"""Compare ideal and published-topology serial drivers in the reference output fixture."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

from circuit import load, node
from output_circuit import output_circuit
from failure_evidence import solver_diagnostic

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_dc_reference():
    dc_reference_path = HERE / 'reports/ttl7406/dc-candidate/report.json'
    dc_reference = json.loads(dc_reference_path.read_text())
    if (not dc_reference['dcPointsWithinPublishedLimits'] or dc_reference['inputReverseBetaOverride'] != .01
            or dc_reference['sources']['ttl7406_nominal.cir'] != sha(HERE / 'ttl7406_nominal.cir')):
        raise ValueError('Serial driver differs from retained DC candidate')
    return sha(dc_reference_path)


def driver_circuit(components, profile, cable_pf):
    if profile not in ('nominal', '7406-dc'):
        raise ValueError('Unknown serial driver profile')
    lines, metadata = output_circuit(components, cable_pf=cable_pf)
    device = components['A1']
    if device['type'] != '7406' or node(device['pins']['7']) != '0':
        raise ValueError('Unexpected serial driver package or ground')
    supply = node(device['pins']['14'])
    lines.append(f'Vdriver_supply {supply} driver_vp 0')
    if profile == '7406-dc':
        for label in ('data', 'clock'):
            output = metadata['serial'][label]['board']
            old = f'S{label} {output} 0 {label}_intent 0 OUTPUT_SINK_NOMINAL'
            if lines.count(old) != 1:
                raise ValueError('Unexpected reference output switch: ' + label)
            lines[lines.index(old)] = f'X{label} {label}_intent {output} driver_vp 0 TTL7406_NOMINAL input_br=.01'
        model = '.model OUTPUT_SINK_NOMINAL SW(RON=20 ROFF=1t VT=2.5 VH=0)'
        if lines.count(model) != 1:
            raise ValueError('Unexpected reference sink model')
        lines.remove(model)
        if any('OUTPUT_SINK_NOMINAL' in line for line in lines):
            raise ValueError('Unclassified remaining output switch')
        lines += (HERE / 'ttl7406_nominal.cir').read_text().splitlines()
    metadata['serialDriver'] = {
        'profile': profile, 'supplyPin': 'A1:14', 'groundPin': 'A1:7',
        'modelQualified': False,
        'scope': 'Data and clock gates only; remaining A1 gates and other controller IC supply currents are not modeled here',
        'assumptions': 'Ideal 20-ohm sink' if profile == 'nominal' else
                       'Published resistor topology, generic semiconductors, input reverse beta .01; DC candidate without storage or junction capacitance calibration',
    }
    return lines, metadata


def simulate(root, profile, step, cable, components, executable, env):
    out = root / f'{profile}-{step}ns-{cable}pf'
    out.mkdir()
    lines, metadata = driver_circuit(components, profile, cable)
    ground = metadata['hostGround']
    signals = [f'v({metadata["serial"][label]["cable"]},{ground})' for label in ('data', 'clock')]
    signals += ['v(n_p5V)', 'i(Vhost)', 'i(Vdriver_supply)', 'i(Vdata)', 'i(Vclock)']
    deck = '\n'.join([
        'Serial driver topology fixture; no firmware or historical timing qualification',
        f'Vhost {metadata["hostSupply"]} {ground} 5', *lines,
        'Vdata data_intent 0 PWL(0 0 10u 0 10.01u 5 20u 5 20.01u 0 40u 0)',
        'Vclock clock_intent 0 PWL(0 0 12u 0 12.01u 5 22u 5 22.01u 0 40u 0)',
        'Vsiso siso_intent 0 0', 'Vcaps caps_intent 0 0',
        '.save ' + ' '.join(signals), '.control', 'set wr_singlescale',
        'set wr_vecnames', 'set numdgt=17', f'tran {step}n 40u',
        'wrdata trace.txt ' + ' '.join(signals), 'quit', '.endc', '.end', ''])
    (out / 'probe.cir').write_text(deck)
    proc = subprocess.run([str(executable), '-n', '-b', 'probe.cir'], cwd=out,
                          env=env, capture_output=True, text=True, timeout=60)
    log = proc.stdout + proc.stderr
    (out / 'ngspice.log').write_text(log)
    proc.check_returncode()
    diagnostic = solver_diagnostic(log)
    if diagnostic:
        raise ValueError(diagnostic)
    rows = [list(map(float, line.split())) for line in (out / 'trace.txt').read_text().splitlines()[1:]]
    if (not rows or any(len(row) != 8 or not all(map(math.isfinite, row)) for row in rows)
            or rows[0][0] > 1e-9 or abs(rows[-1][0] - 40e-6) > 1e-12
            or any(b[0] < a[0] or b[0] - a[0] > step * 1e-9 + 1e-15 for a, b in zip(rows, rows[1:]))):
        raise ValueError('Invalid or incomplete output waveform')
    samples = [min(rows, key=lambda row: abs(row[0] - time)) for time in (2e-6, 16e-6, 36e-6)]
    for index, row in enumerate(samples):
        if not all(v < .8 if index == 1 else v > 2 for v in row[1:3]):
            raise ValueError('Serial drive/release failed at cable receiver')
        if profile == '7406-dc' and row[5] <= .001:
            raise ValueError('Transistor driver supply current not observed')
        if profile == 'nominal' and abs(row[5]) > 1e-12:
            raise ValueError('Ideal sink unexpectedly draws driver supply current')
    rises = []
    for column, start in ((1, 20e-6), (2, 22e-6)):
        times = []
        for level in (.8, 2):
            crossings = [a[0] + (level - a[column]) * (b[0] - a[0]) / (b[column] - a[column])
                         for a, b in zip(rows, rows[1:])
                         if start <= a[0] < start + 8e-6 and a[column] < level <= b[column]]
            if len(crossings) != 1:
                raise ValueError('Receiver release lacks a unique crossing')
            times.append(crossings[0])
        rises.append(times[1] - times[0])
    return {'profile': profile, 'stepNs': step, 'cablePf': cable, 'circuit': metadata,
            'signals': signals, 'samples': samples,
            'currentSignConvention': 'Vhost/data/clock source currents are negative when supplying the circuit; Vdriver_supply is positive into the modeled gates',
            'receiverRiseSeconds08to2V': rises,
            'artifacts': {name: sha(out / name) for name in ('probe.cir', 'trace.txt', 'ngspice.log')}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', default='ngspice')
    parser.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-analog/ttl7406-outputs')
    args = parser.parse_args()
    located = shutil.which(args.ngspice)
    if located is None:
        parser.error('ngspice executable not found')
    executable = Path(located).resolve()
    dc_reference_digest = checked_dc_reference()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / 'spinit').write_text('* Pure SPICE output fixture; no external initialization or code models.\n')
    env = dict(os.environ, SPICE_SCRIPTS=str(out))
    report = {'passed': False, 'qualified': False, 'scope': __doc__,
              'dcCandidateReportSha256': dc_reference_digest,
              'executableSha256': sha(executable), 'spinitSha256': sha(out / 'spinit'),
              'sources': {name: sha(HERE / name) for name in
                          ('ttl7406_output_probe.py', 'ttl7406_nominal.cir', 'output_circuit.py', 'circuit.py', 'failure_evidence.py')},
              'limitations': 'Numerical fixture checks only. No transistor storage/capacitance, device-corner, full-package, firmware, or specimen qualification.',
              'runs': []}
    try:
        components, report['connectivitySha256'] = load()
        for profile in ('nominal', '7406-dc'):
            profile_runs = []
            for cable in (1000, 2000):
                pair = [simulate(out, profile, step, cable, components, executable, env) for step in (10, 5)]
                report['runs'] += pair
                profile_runs += pair
                for a, b in zip(*(run['receiverRiseSeconds08to2V'] for run in pair)):
                    if abs(a / b - 1) > .01:
                        raise ValueError('Receiver rise interval fails 1% timestep refinement')
            for a, b in zip(profile_runs[1]['receiverRiseSeconds08to2V'], profile_runs[3]['receiverRiseSeconds08to2V']):
                if b < 1.5 * a:
                    raise ValueError('Doubled cable capacitance does not slow release as expected')
        if sha(executable) != report['executableSha256']:
            raise ValueError('Simulator changed during output fixture')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(out / 'report.json')


if __name__ == '__main__':
    main()
