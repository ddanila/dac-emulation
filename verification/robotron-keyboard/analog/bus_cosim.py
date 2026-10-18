#!/usr/bin/env python3
"""Exercise independent HDL bus drivers through SPICE loads and receiver feedback."""
import argparse
import json
import math
import re
import subprocess
from pathlib import Path

from bus_driver import wiring
from circuit import load
from clock_output_probe import sha
from electrical_bus_interface import generate
from failure_evidence import solver_diagnostic
from ngspice_runtime import identify, verify

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bridge', type=Path, default=ROOT / 'build/keyboard-controller-analog/bridge/bridge.json')
    parser.add_argument('--ngspice', default='ngspice')
    parser.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-analog/bus-feedback')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    components, connectivity = load()
    report = {'passed': False, 'qualified': False, 'scope': __doc__,
              'connectivitySha256': connectivity, 'runs': [],
              'sources': {name: sha(HERE / name) for name in (
                  'bus_cosim.py', 'bus_cosim.v', 'bus_driver.py', 'bus_load.py',
                  'bus_inventory.py', 'bus_limits.json', 'electrical_bus_interface.py',
                  'controller_interface.py', 'logic_control.py', 'circuit.py',
                  'clock_output_probe.py', 'failure_evidence.py', 'ngspice_runtime.py')},
              'chipsSha256': sha(HERE.parent / 'chips.v')}
    try:
        bridge = json.loads(args.bridge.read_text())
        for library in bridge['libraries'].values():
            if sha(Path(library['path'])) != library['sha256'] or any(c in library['path'] for c in ('"', '\n')):
                raise ValueError('Invalid bridge input')
        report['bridge'] = bridge
        runtime, env = identify(args.ngspice, None)
        report['ngspiceRuntime'] = runtime
        libs = {key: value['path'] for key, value in bridge['libraries'].items()}
        limits = json.loads((HERE / 'bus_limits.json').read_text())
        lines, fixture = wiring(components, limits, {'I8282': 12, '7406': 3})
        report['fixture'] = fixture
        report['initialConditions'] = 'All bus pins 0 V; 1 teraohm numerical shunts to ground; release retention is fixture-specific.'
        for step in (5, 2.5):
            directory = out / f'step-{step}ns'
            directory.mkdir()
            (directory / 'controller.v').write_text(generate())
            subprocess.run(['iverilog', '-g2012', '-s', 'bus_cosim', '-o', str(directory / 'bus.vvp'),
                            str(directory / 'controller.v'), str(HERE.parent / 'chips.v'), str(HERE / 'bus_cosim.v')], check=True)
            def vector(prefix, count):
                return ' '.join(f'{prefix}{i}' for i in reversed(range(count)))
            signals = ' '.join(f'v(n_D{i})' for i in range(8)) + ' i(Vcc)'
            deck = '\n'.join(['Live bus feedback with linear endpoint stress drivers', 'Vcc n_p5V 0 5', *lines,
                *[f'Rnumerical{i} n_D{i} 0 1e12' for i in range(8)],
                '.ic ' + ' '.join(f'v(n_D{i})=0' for i in range(8)),
                'Vfixture fixture_clk 0 PULSE(0 5 100n 1n 1n 2u 4u)',
                'Afixture [fixture_clk] [dclk] clock_receiver',
                f'Abus [{vector("n_D",8)}] [{vector("sense",8)}] receiver',
                '.model receiver adc_bridge(in_low=.8 in_high=2)',
                '.model clock_receiver adc_bridge(in_low=1.4 in_high=1.4)',
                f'Ahdl [dclk {vector("sense",8)}] [{vector("low",24)} {vector("high",24)}] hdl',
                f'.model hdl d_cosim simulation="{libs["shim"]}" sim_args=["bus.vvp"] delay=10n',
                f'+ lib_args=["{libs["libvvp"]}" "{libs["vpi"]}"]',
                f'Alow [{vector("low",24)}] [{vector("bus_low_",24)}] drive',
                f'Ahigh [{vector("high",24)}] [{vector("bus_high_",24)}] drive',
                '.model drive dac_bridge(out_low=0 out_high=5 out_undef=2.5 t_rise=1n t_fall=1n)',
                '.save ' + signals, '.control', 'set wr_singlescale', 'set wr_vecnames', 'set numdgt=17',
                f'tran {step}n 29u uic', 'wrdata trace.txt ' + signals, 'quit', '.endc', '.end', ''])
            (directory / 'probe.cir').write_text(deck)
            verify(runtime)
            with (directory / 'ngspice.log').open('w') as log:
                subprocess.run([runtime['executable']['path'], '-n', '-b', 'probe.cir'], cwd=directory,
                               env=env, stdout=log, stderr=subprocess.STDOUT, timeout=120, check=True)
            verify(runtime)
            log = (directory / 'ngspice.log').read_text()
            if solver_diagnostic(log):
                raise ValueError('Bus feedback solver or HDL diagnostics')
            reads = re.findall(r'^BUS_READ (\d+) (\d+) ([0-9a-fxz]+)$', log, re.M)
            expected = ['00', 'ff', '00', 'a5', '5a', '00', 'a5', 'a5']
            if len(reads) != len(expected) or 'BUS_FEEDBACK_PASS' not in log:
                raise ValueError('Incomplete bus feedback fixture')
            if [(int(phase), value) for _, phase, value in reads] != list(enumerate(expected)):
                raise ValueError('Unexpected bus receiver states: ' + repr(reads))
            rows = [list(map(float, line.split())) for line in (directory / 'trace.txt').read_text().splitlines()[1:]]
            if not rows or any(len(row) != 10 or not all(map(math.isfinite, row)) for row in rows):
                raise ValueError('Invalid bus waveform')
            if abs(rows[-1][0] - 29e-6) > 1e-12:
                raise ValueError('Incomplete bus waveform')
            sampled = []
            for time_ps, phase, value in reads:
                row = min(rows, key=lambda row: abs(row[0] - int(time_ps) * 1e-12))
                if abs(row[0] - int(time_ps) * 1e-12) > step * 1e-9 + 1e-12:
                    raise ValueError('Missing bus read sample')
                if any(not (volts > 2 if int(value, 16) & (1 << bit) else volts < .8)
                       for bit, volts in enumerate(row[1:9])):
                    raise ValueError('Receiver logic differs from electrical voltage')
                sampled.append({'phase': int(phase), 'timeSeconds': row[0], 'busVolts': row[1:9],
                                'supplyCurrentAmps': -row[9]})
            current = sampled[5]['supplyCurrentAmps']
            drivers = fixture['drivers']
            expected_current = 4 * 5 / (drivers[0]['lowOhms'] + drivers[1]['highOhms']) + 4 * 5 / (drivers[1]['lowOhms'] + drivers[0]['highOhms'])
            if abs(current - expected_current) / expected_current > .001:
                raise ValueError('Contention current differs from fixture circuit')
            report['runs'].append({'stepNs': step, 'reads': reads, 'samples': sampled,
                                   'expectedContentionAmps': expected_current,
                                   'files': {p.name: sha(p) for p in directory.iterdir()}})
        if [r[1:] for r in report['runs'][0]['reads']] != [r[1:] for r in report['runs'][1]['reads']]:
            raise ValueError('Receiver states change under refinement')
        coarse, fine = report['runs']
        comparison = {
            'maximumSampleVoltageDifference': max(abs(x - y)
                for a, b in zip(coarse['samples'], fine['samples'])
                for x, y in zip(a['busVolts'], b['busVolts'])),
            'maximumSampleCurrentDifferenceAmps': max(abs(a['supplyCurrentAmps'] - b['supplyCurrentAmps'])
                for a, b in zip(coarse['samples'], fine['samples'])),
            'maximumReadTimeDifferencePs': max(abs(int(a[0]) - int(b[0]))
                for a, b in zip(coarse['reads'], fine['reads'])),
            'budgets': {'sampleVolts': .001, 'sampleAmps': 1e-6, 'readTimePs': 5000},
            'boundary': 'Numerical fixture convergence only; not device calibration or transition timing qualification.',
        }
        report['comparison'] = comparison
        if (comparison['maximumSampleVoltageDifference'] > .001 or
            comparison['maximumSampleCurrentDifferenceAmps'] > 1e-6 or
            comparison['maximumReadTimeDifferencePs'] > 5000):
            raise ValueError('Bus fixture changes under timestep refinement')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(out / 'report.json')


if __name__ == '__main__':
    main()
