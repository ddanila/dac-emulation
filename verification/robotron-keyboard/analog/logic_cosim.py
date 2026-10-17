#!/usr/bin/env python3
"""Close generated HDL control-driver/SPICE pullup/HDL latch and flip-flop feedback."""
import argparse
import json
import math
import re
import subprocess
from pathlib import Path

from circuit import load
from controller_interface import generate
from logic_control import wiring
from clock_output_probe import sha
from failure_evidence import solver_diagnostic
from ngspice_runtime import identify, verify

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bridge', type=Path, default=ROOT / 'build/keyboard-controller-analog/bridge/bridge.json')
    parser.add_argument('--ngspice', default='ngspice')
    parser.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-analog/logic-feedback')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    components, connectivity = load()
    report = {'passed': False, 'qualified': False, 'scope': __doc__, 'runs': [],
              'boundary': 'Bus fixture, not CPU firmware; nominal sinks and 1.4 V I/O-active clock crossing. No device, propagation or power-on calibration',
              'connectivitySha256': connectivity,
              'sources': {name: sha(HERE / name) for name in ('logic_cosim.py', 'logic_cosim.v', 'logic_control.py', 'controller_interface.py', 'circuit.py', 'ngspice_runtime.py', 'failure_evidence.py', 'clock_output_probe.py')},
              'chipsSha256': sha(HERE.parent / 'chips.v')}
    try:
        bridge = json.loads(args.bridge.read_text())
        for library in bridge['libraries'].values():
            if sha(Path(library['path'])) != library['sha256'] or any(c in library['path'] for c in ('"', '\n')):
                raise ValueError('Invalid bridge input')
        report['bridge'] = bridge
        runtime, env = identify(args.ngspice, None)
        report['ngspiceRuntime'] = runtime
        report['iverilog'] = subprocess.run(['iverilog', '-V'], check=True, capture_output=True, text=True).stdout.splitlines()[0]
        libs = {key: value['path'] for key, value in bridge['libraries'].items()}
        for load_pf in (0, 10):
            pair = []
            for step in (1, .5):
                directory = out / f'load-{load_pf}pf-step-{step}ns'
                directory.mkdir()
                (directory / 'controller_analog.v').write_text(generate(explicit_cpu_drive=True, resolved_bus=True))
                subprocess.run(['iverilog', '-g2012', '-s', 'logic_cosim', '-o', str(directory / 'logic.vvp'),
                                str(directory / 'controller_analog.v'), str(HERE.parent / 'chips.v'), str(HERE / 'logic_cosim.v')], check=True)
                lines, _, info = wiring(components, load_pf)
                nets = info['nets']
                signals = ' '.join(f'v({nets[name]})' for name in ('latchEnable', 'flipFlopRelease', 'ioActive'))
                deck = '\n'.join(['Live electrical logic-control feedback', 'Vcc n_p5V 0 5', *lines,
                    'Vfixture fixture_clk 0 PULSE(0 5 100n 1n 1n 50n 200n)',
                    'Afixture [fixture_clk] [dclk] clock_receiver',
                    f'Alevels [{nets["latchEnable"]} {nets["flipFlopRelease"]}] [d_oe d_ff] level_receiver',
                    f'Aclock [{nets["ioActive"]}] [d_io] clock_receiver',
                    '.model level_receiver adc_bridge(in_low=.8 in_high=2)',
                    '.model clock_receiver adc_bridge(in_low=1.4 in_high=1.4)',
                    'Ahdl [dclk d_io d_ff d_oe] [d_sink1 d_sink0] hdl',
                    f'.model hdl d_cosim simulation="{libs["shim"]}" sim_args=["logic.vvp"] delay=10n',
                    f'+ lib_args=["{libs["libvvp"]}" "{libs["vpi"]}"]',
                    'Adrive [d_sink0 d_sink1] [control_latchEnable_sink control_ioActive_sink] drive',
                    '.model drive dac_bridge(out_low=0 out_high=5 out_undef=2.5 t_rise=1n t_fall=1n)',
                    '.save ' + signals, '.control', 'set wr_singlescale', 'set wr_vecnames', 'set numdgt=17',
                    f'tran {step}n 2u', 'wrdata trace.txt ' + signals, 'quit', '.endc', '.end', ''])
                (directory / 'probe.cir').write_text(deck)
                verify(runtime)
                with (directory / 'ngspice.log').open('w') as log:
                    subprocess.run([runtime['executable']['path'], '-n', '-b', 'probe.cir'], cwd=directory,
                                   env=env, stdout=log, stderr=subprocess.STDOUT, timeout=60, check=True)
                verify(runtime)
                log = (directory / 'ngspice.log').read_text()
                if solver_diagnostic(log):
                    raise ValueError('Logic feedback solver or HDL diagnostics')
                reads = re.findall(r'^LOGIC_READ (\d+) (\d+) ([0-9a-fx]+) ([01xz]+)$', log, re.M)
                if len(reads) != 10 or 'LOGIC_FEEDBACK_PASS' not in log:
                    raise ValueError('Incomplete control feedback fixture')
                for index, (_, phase, data, leds) in enumerate(reads):
                    expected = {3: 'a5', 4: 'a5', 5: '3c', 6: '3c', 7: 'ff', 8: 'ff', 9: 'ff'}.get(index)
                    expected_leds = '00' if index < 5 else '10'
                    if int(phase) != index or (expected is not None and data != expected) or (index >= 1 and leds != expected_leds):
                        raise ValueError(f'Unexpected returned bus/LED state at phase {index}: {data}/{leds}')
                rows = [list(map(float, line.split())) for line in (directory / 'trace.txt').read_text().splitlines()[1:]]
                if not rows or any(len(row) != 4 or not all(map(math.isfinite, row)) for row in rows):
                    raise ValueError('Invalid control feedback waveform')
                if rows[0][0] > 1e-12 or abs(rows[-1][0] - 2e-6) > 1e-12:
                    raise ValueError('Incomplete control feedback waveform')
                sampled = []
                for time_ps, phase, _, _ in reads[3:]:
                    phase = int(phase)
                    time = int(time_ps) * 1e-12
                    row = min(rows, key=lambda row: abs(row[0] - time))
                    expected_levels = [phase >= 7, True, phase == 5]
                    if abs(row[0] - time) > step * 1e-9 + 1e-12 or any(
                            not (value > 2 if high else value < .8) for value, high in zip(row[1:], expected_levels)):
                        raise ValueError('Physical control voltages disagree with fixture read phase')
                    sampled.append({'phase': phase, 'sampleSeconds': row[0], 'volts': row[1:]})
                run = {'fixture': info, 'stepNs': step, 'reads': reads, 'deckSha256': sha(directory / 'probe.cir'),
                       'controlVoltsAtReads': sampled,
                       'generatedHdlSha256': sha(directory / 'controller_analog.v'), 'compiledHdlSha256': sha(directory / 'logic.vvp'),
                       'traceSha256': sha(directory / 'trace.txt'), 'logSha256': sha(directory / 'ngspice.log')}
                report['runs'].append(run)
                pair.append(run)
            if [r[1:] for r in pair[0]['reads']] != [r[1:] for r in pair[1]['reads']]:
                raise ValueError('Control feedback values change under refinement')
            if max(abs(int(a[0]) - int(b[0])) for a, b in zip(pair[0]['reads'], pair[1]['reads'])) > 2000:
                raise ValueError('Fixture observation times differ by more than 2 ns')
            for a, b in zip(pair[0]['controlVoltsAtReads'], pair[1]['controlVoltsAtReads']):
                if max(abs(x - y) for x, y in zip(a['volts'], b['volts'])) > .01:
                    raise ValueError('Sampled control voltages differ by more than 10 mV under refinement')
        for library in bridge['libraries'].values():
            if sha(Path(library['path'])) != library['sha256']:
                raise ValueError('Bridge changed during control fixture')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(out / 'report.json')


if __name__ == '__main__':
    main()
