#!/usr/bin/env python3
"""Close the HDL column-driver/SPICE contact/sense/HDL latch feedback loop."""
import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

from failure_evidence import solver_diagnostic

from circuit import load
from controller_interface import generate
from matrix import LATCH_LOADS, matrix_circuit, reached_rows
from matrix_probe import SELECTIONS

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args, components, libs, name, contacts, step_ns):
    out = args.out.resolve() / f'{name}-{step_ns}ns'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'trace.txt').unlink(missing_ok=True)
    (out / 'controller_analog.v').write_text(generate())
    vectors = []
    for selection in SELECTIONS:
        address = 0x8000 | sum(1 << col for col in selection)
        expected = sum(1 << row for row in reached_rows(contacts, selection))
        vectors.append(f'{address:04x}{expected:02x}')
    (out / 'matrix-vectors.hex').write_text('\n'.join(vectors) + '\n')
    subprocess.run([args.iverilog, '-g2012', '-s', 'matrix_cosim',
                    '-Pmatrix_cosim.COUNT=' + str(len(vectors)), '-o', str(out / 'matrix.vvp'),
                    str(out / 'controller_analog.v'), str(HERE.parent / 'chips.v'),
                    str(HERE / 'matrix_cosim.v')], check=True)
    lines, metadata = matrix_circuit(components, latch_load=args.latch_load)
    lines = ['Robotron live HDL/electrical matrix feedback fixture', 'Vcc n_p5V 0 5', *lines]
    for index in range(104):
        lines.append(f'Vcontact{index} contact{index} 0 {5 if index in contacts else 0}')
    inputs = ' '.join(f'dsense{i}' for i in reversed(range(8)))
    analog_inputs = ' '.join(f'n_SENSE{i}' for i in reversed(range(8)))
    outputs = ' '.join(f'dcol{i}' for i in reversed(range(13)))
    analog_outputs = ' '.join(f'sink{i}' for i in reversed(range(13)))
    lines += [f'Ainput [{analog_inputs}] [{inputs}] receiver',
              '.model receiver adc_bridge(in_low=0.8 in_high=2)',
              f'Ahdl [{inputs}] [{outputs}] hdl',
              f'.model hdl d_cosim simulation="{libs["shim"]}" sim_args=["matrix.vvp"] delay=1n',
              f'+ lib_args=["{libs["libvvp"]}" "{libs["vpi"]}"]',
              f'Adrive [{outputs}] [{analog_outputs}] drive',
              '.model drive dac_bridge(out_low=0 out_high=5 out_undef=2.5 t_rise=1n t_fall=1n)',
              '.save ' + ' '.join(f'v({n})' for n in metadata['outputs']),
              '.control', 'set wr_singlescale', 'set wr_vecnames',
              f'tran {step_ns}n 170u',
              'wrdata trace.txt ' + ' '.join(f'v({n})' for n in metadata['outputs']),
              'quit', '.endc', '.end']
    (out / 'matrix.cir').write_text('\n'.join(lines) + '\n')
    with (out / 'ngspice.log').open('w') as log:
        subprocess.run([args.ngspice, '-n', '-b', 'matrix.cir'], cwd=out, stdout=log,
                       stderr=subprocess.STDOUT, check=True, timeout=120)
    log = (out / 'ngspice.log').read_text()
    if solver_diagnostic(log):
        raise ValueError('Bridge/solver/HDL diagnostics: ' + str(out / 'ngspice.log'))
    reads = re.findall(r'^MATRIX_READ (\d+) (\d+) ([0-9a-f]+) ([0-9a-f]+)$', log, re.M)
    if len(reads) != len(vectors) or f'MATRIX_FEEDBACK_PASS {len(vectors)}' not in log:
        raise ValueError('Live HDL checks did not complete')
    for index, (time_ps, number, address, result) in enumerate(reads):
        if int(number) != index or f'{int(address,16):04x}{int(result,16):02x}' != vectors[index]:
            raise ValueError('Read trace disagrees with expected bus stimulus')
        if int(time_ps) != (14000 + index*10000)*1000:
            raise ValueError('HDL fixture time drift')
    samples = [[float(v) for v in line.split()] for line in (out / 'trace.txt').read_text().splitlines()[1:]]
    if not samples or any(len(row) != 9 or not all(map(math.isfinite, row)) for row in samples):
        raise ValueError('Invalid analog trace')
    if samples[0][0] > 1e-9 or samples[-1][0] < 170e-6:
        raise ValueError('Incomplete transient trace')
    sampled = []
    for index, selection in enumerate(SELECTIONS):
        row = min(samples, key=lambda row: abs(row[0] - (14 + index*10)*1e-6))
        expected = reached_rows(contacts, selection)
        for bit, voltage in enumerate(row[1:]):
            if not (voltage > 2 if bit in expected else voltage < .8):
                raise ValueError('Analog sample disagrees with HDL read result')
        sampled.append(row[1:])
    return {'case': name, 'contacts': sorted(contacts), 'stepNs': step_ns,
            'reads': reads, 'senseVoltsAtReads': sampled,
            'deckSha256': sha(out / 'matrix.cir'),
            'generatedHdlSha256': sha(out / 'controller_analog.v'),
            'vectorsSha256': sha(out / 'matrix-vectors.hex')}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bridge', type=Path, default=ROOT / 'build/keyboard-controller-analog/bridge/bridge.json')
    p.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-analog/matrix-feedback')
    p.add_argument('--ngspice', default='ngspice')
    p.add_argument('--iverilog', default='iverilog')
    p.add_argument('--latch-load', choices=LATCH_LOADS, default='ideal')
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / 'report.json'
    path.unlink(missing_ok=True)
    report = {'passed': False, 'scope': __doc__, 'runs': [],
              'assumptions': {'contacts': 'Diode-free external switch fixture, not specimen key construction',
                              'models': 'Nominal matrix.py semiconductors, contacts, drivers and latch loading',
                              'stimulus': 'HDL bus fixture, not CPU firmware; no bounce or changing contacts',
                              'latchLoad': args.latch_load, 'thresholdVolts': [.8, 2], 'bridgeDelaySeconds': 1e-9},
              'sources': {name: sha(HERE / name) for name in ('failure_evidence.py', 'matrix_cosim.py', 'matrix_cosim.v',
                         'matrix.py', 'latch_limits.json', 'matrix_probe.py', 'controller_interface.py', 'circuit.py')},
              'chipsSha256': sha(HERE.parent / 'chips.v')}
    try:
        components, report['connectivitySha256'] = load()
        bridge = json.loads(args.bridge.read_text())
        for lib in bridge['libraries'].values():
            if sha(Path(lib['path'])) != lib['sha256']:
                raise ValueError('Bridge library provenance mismatch')
        report['bridge'] = bridge
        libs = {key: val['path'] for key, val in bridge['libraries'].items()}
        if any('"' in v or '\n' in v for v in libs.values()):
            raise ValueError('Unsupported library path')
        report['ngspice'] = subprocess.check_output([args.ngspice, '--version'], text=True).strip()
        report['iverilog'] = subprocess.run([args.iverilog, '-V'], capture_output=True, text=True, check=True).stdout.splitlines()[0]
        for name, contacts in [('open', set()), ('single', {61}), ('rectangle', {0, 8, 9}), ('all', set(range(104)))]:
            pair = []
            for step in (20, 10):
                result = run(args, components, libs, name, contacts, step)
                pair.append(result)
                report['runs'].append(result)
            if pair[0]['reads'] != pair[1]['reads']:
                raise ValueError('Bus result changes under timestep refinement')
            for a, b in zip(pair[0]['senseVoltsAtReads'], pair[1]['senseVoltsAtReads']):
                if max(abs(x-y) for x,y in zip(a,b)) > .01:
                    raise ValueError('Settled sense voltages change by more than 10 mV under refinement')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        path.write_text(json.dumps(report, indent=2) + '\n')
    print(path)


if __name__ == '__main__':
    main()
