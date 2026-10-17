#!/usr/bin/env python3
"""Exercise the schematic clock pullup and BR1 against U880 reference input levels."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

from circuit import load, node, elements
from failure_evidence import solver_diagnostic

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MODELS = ('ls_nand_nominal.cir', 'ls_nand_dc.cir', 'ls_nand_pullup.cir')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wiring(components, capacitance):
    cpu, gate, bridge = (components[ref] for ref in ('A5', 'A7', 'BR1'))
    if cpu['type'] != 'U880' or gate['type'] != 'DL000' or bridge['type'] != 'BRIDGE':
        raise ValueError('Unexpected clock-path devices')
    if (gate['pins']['9'] != gate['pins']['10'] or gate['pins']['8'] != bridge['pins']['1']
            or cpu['pins']['6'] != bridge['pins']['2']
            or cpu['pins']['11'] != gate['pins']['14'] or cpu['pins']['29'] != gate['pins']['7']
            or set(components['R10.3']['pins'].values()) != {cpu['pins']['11'], cpu['pins']['6']}):
        raise ValueError('Clock path no longer matches the fixture boundary')
    ground, supply = node(cpu['pins']['29']), node(cpu['pins']['11'])
    control, output, clock = node(gate['pins']['9']), node(gate['pins']['8']), node(cpu['pins']['6'])
    lines, _ = elements(components, ('R10.3',))
    lines += [f'RBR1 {output} {clock} .001', f'Ccpu {clock} {ground} {capacitance:.17g}',
              f'Xgate {control} {control} {output} {supply} {ground} LS_NAND_NOMINAL']
    return lines, {'ground': ground, 'supply': supply, 'control': control, 'output': output, 'clock': clock}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', default='ngspice')
    parser.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-analog/clock-output')
    args = parser.parse_args()
    found = shutil.which(args.ngspice)
    if found is None:
        parser.error('ngspice executable not found')
    executable = Path(found).resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / 'spinit').write_text('* Pure SPICE clock-output fixture.\n')
    environment = dict(os.environ, SPICE_SCRIPTS=str(out))
    limits = json.loads((HERE / 'cpu_clock_limits.json').read_text())
    components, connectivity_sha = load()
    lines, nets = wiring(components, limits['clockInput']['capacitanceMaximumFarads'])
    report = {'passed': False, 'qualified': False, 'scope': __doc__, 'limits': limits,
              'connectivitySha256': connectivity_sha, 'executableSha256': sha(executable),
              'spinitSha256': sha(out / 'spinit'), 'cases': [],
              'sources': {name: sha(HERE / name) for name in
                          (*MODELS, 'clock_output_probe.py', 'cpu_clock_limits.json', 'circuit.py', 'failure_evidence.py')},
              'limitations': 'Driven final NAND stage only; not oscillator feedback or firmware. CPU capacitance is a reference maximum, leakage is omitted. Candidate output I/V and switching remain uncalibrated.'}
    try:
        for model in MODELS:
            for supply in (4.75, 5, 5.25):
                directory = out / f'{Path(model).stem}-{supply}V'
                directory.mkdir()
                (directory / 'model.cir').write_bytes((HERE / model).read_bytes())
                voltages = [f'v({nets[key]})' if nets['ground'] == '0' else
                            f'v({nets[key]},{nets["ground"]})' for key in ('clock', 'output')]
                signals = ' '.join([*voltages, 'i(Vcc)'])
                deck = '\n'.join([
                    'Clock pullup fixture; generic gate parameters, not specimen qualification',
                    '.include model.cir', '.temp 25', f'Vcc {nets["supply"]} {nets["ground"]} {supply}',
                    f'Vin {nets["control"]} {nets["ground"]} PWL(0 0 200n 0 201n 5 400n 5 401n 0 1u 0)',
                    *lines, '.save ' + signals, '.control', 'set wr_singlescale', 'set wr_vecnames',
                    'set numdgt=17', 'tran .5n 1u', 'wrdata trace.txt ' + signals,
                    'quit', '.endc', '.end', ''])
                (directory / 'probe.cir').write_text(deck)
                result = subprocess.run([str(executable), '-n', '-b', 'probe.cir'], cwd=directory,
                                        env=environment, capture_output=True, text=True, timeout=60)
                log = result.stdout + result.stderr
                (directory / 'ngspice.log').write_text(log)
                result.check_returncode()
                if solver_diagnostic(log):
                    raise ValueError(solver_diagnostic(log))
                rows = [list(map(float, line.split())) for line in (directory / 'trace.txt').read_text().splitlines()[1:]]
                if (not rows or any(len(row) != 4 or not all(map(math.isfinite, row)) for row in rows)
                        or rows[0][0] > 1e-12 or abs(rows[-1][0] - 1e-6) > 1e-12
                        or any(b[0] < a[0] or b[0]-a[0] > .501e-9 for a, b in zip(rows, rows[1:]))):
                    raise ValueError('Incomplete or invalid clock-output trace')
                samples = [min(rows, key=lambda row: abs(row[0]-time)) for time in (100e-9, 300e-9, 900e-9)]
                high_minimum = supply - limits['clockInput']['highMinimumSupplyDropVolts']
                within = (samples[1][1] <= limits['clockInput']['lowMaximumVolts']
                          and all(row[1] >= high_minimum for row in (samples[0], samples[2])))
                if within != (model == 'ls_nand_pullup.cir'):
                    raise ValueError('Unexpected clock-level regression: ' + model)
                report['cases'].append({'model': model, 'supplyVolts': supply, 'temperatureC': 25, 'samples': samples,
                    'sampleColumns': ['timeSeconds', 'cpuClockVolts', 'gateOutputVolts', 'supplySourceAmps'],
                    'clockLevelsWithinReference': within, 'requiredHighMinimumVolts': high_minimum,
                    'assumedCpuCapacitanceFarads': limits['clockInput']['capacitanceMaximumFarads'],
                    'artifacts': {name: sha(directory / name) for name in ('model.cir', 'probe.cir', 'trace.txt', 'ngspice.log')}})
        if sha(executable) != report['executableSha256']:
            raise ValueError('Simulator changed during clock-output fixture')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(out / 'report.json')


if __name__ == '__main__':
    main()
