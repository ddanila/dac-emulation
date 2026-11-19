"""Check the live T200 functional NAND against the SN74H00 class limits."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

import signal_path

ROOT = Path(__file__).resolve().parent
MODEL = ROOT / 'circuits/signal-path-models.cir'


def fixture_prefix():
    params = '\n'.join(f'.param {key}={value[0]}'
                       for key, value in signal_path.BOUNDS.items())
    return params + '\n' + MODEL.read_text()


def solve(deck, expressions):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'run.cir'
        path.write_text(deck)
        result = subprocess.run(['ngspice', '-b', str(path)],
                                capture_output=True, text=True, timeout=30)
    if result.returncode or re.search(r'error|warning|singular matrix',
                                      result.stdout + result.stderr, re.I):
        raise RuntimeError('T200 class fixture failed: ' + result.stdout + result.stderr)
    values = {}
    for expression in expressions:
        match = re.search(r'^' + re.escape(expression) + r' = ([^\s]+)',
                          result.stdout, re.M)
        if not match:
            raise RuntimeError('missing fixture value: ' + expression)
        values[expression] = float(match.group(1))
    return values


def dc_case(a, b, *, vcc=5, load='Rload y1 0 1G'):
    deck = f'''T200 isolated DC class fixture
{fixture_prefix()}
Vcc supply 0 {vcc}
Va a 0 {a}
Vb b 0 {b}
Xchip a b y1 a b y2 0 y3 a b y4 a b supply T200_BOUND
{load}
.control
op
print v(y1) i(Vcc) i(Va)
.endc
.end
'''
    values = solve(deck, ('v(y1)', 'i(vcc)', 'i(va)'))
    return dict(input_a_v=a, input_b_v=b, supply_v=vcc,
                output_v=values['v(y1)'],
                supply_current_a=-values['i(vcc)'],
                input_a_current_a=-values['i(va)'] / 4,
                input_a_pins_driven=4)


def crossing(rows, column, level, start=19e-9):
    for before, after in zip(rows, rows[1:]):
        if before[0] >= start and (before[column] - level) * (after[column] - level) <= 0:
            return before[0] + (after[0] - before[0]) * (level - before[column]) / (after[column] - before[column])
    raise ValueError('transient did not cross requested level')


def transient(rising_output, high_v, low_v):
    a0, a1 = (4.5, 0) if rising_output else (0, 4.5)
    deck = f'''T200 isolated switching class fixture
{fixture_prefix()}
Vcc supply 0 5
Va a 0 PULSE({a0} {a1} 20n .1n .1n 20n 50n)
Vb b 0 4.5
Xchip a b y1 0 0 y2 0 y3 0 0 y4 0 0 supply T200_BOUND
Rload supply y1 280
Cload y1 0 25p
.control
set wr_singlescale
set wr_vecnames
tran .2n 45n
linearize v(a) v(y1)
wrdata samples.txt v(a) v(y1)
quit
.endc
.end
'''
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)
        (path / 'run.cir').write_text(deck)
        result = subprocess.run(['ngspice', '-b', 'run.cir'], cwd=path,
                                capture_output=True, text=True, timeout=30)
        if result.returncode or re.search(r'error|warning|timestep too small',
                                          result.stdout + result.stderr, re.I):
            raise RuntimeError('T200 switching fixture failed: ' + result.stdout + result.stderr)
        with (path / 'samples.txt').open() as stream:
            next(stream)
            rows = [[float(value) for value in line.split()] for line in stream]
    input_crossing = crossing(rows, 1, 2.25)
    output_crossing = crossing(rows, 2, (high_v + low_v) / 2)
    return dict(direction='low-to-high output' if rising_output else 'high-to-low output',
                input_crossing_s=input_crossing, output_crossing_s=output_crossing,
                propagation_delay_s=output_crossing - input_crossing)


def run():
    logic = {f'{a:g},{b:g}': dc_case(a, b) for a, b in
             ((0, 0), (0, 4.5), (4.5, 0), (4.5, 4.5))}
    vil = dc_case(.8, 4.5, vcc=4.75)
    vih = dc_case(2, 4.5, vcc=4.75)
    high = dc_case(0, 0, vcc=4.75, load='Iload y1 0 .5m')
    high_unloaded = dc_case(0, 0, vcc=4.75, load='Rload y1 0 1G')
    low = dc_case(2.4, 2.4, vcc=4.75, load='Iload supply y1 20m')
    high_bias = dc_case(2.4, 2.4)
    low_bias = dc_case(.4, .4)
    switched_high = dc_case(0, 4.5, load='Rload supply y1 280')
    switched_low = dc_case(4.5, 4.5, load='Rload supply y1 280')
    rise = transient(True, switched_high['output_v'], switched_low['output_v'])
    fall = transient(False, switched_high['output_v'], switched_low['output_v'])
    checks = dict(
        nand_truth=all((logic[key]['output_v'] > 2.4) == (key != '4.5,4.5')
                       for key in logic),
        input_level_limits=vil['output_v'] >= 2.4 and vih['output_v'] <= .4,
        high_output_load=high['output_v'] >= 2.4,
        low_output_load=low['output_v'] <= .4,
        high_input_current=0 <= high_bias['input_a_current_a'] <= 50e-6,
        low_input_current=-2e-3 <= low_bias['input_a_current_a'] <= 0,
        supply_current_high=0 < logic['0,0']['supply_current_a'] <= 16.8e-3,
        supply_current_low=0 < logic['4.5,4.5']['supply_current_a'] <= 40e-3,
        output_current_from_supply=.45e-3 <= high['supply_current_a']
                                   - high_unloaded['supply_current_a'] <= .55e-3,
        propagation_delay=0 < rise['propagation_delay_s'] <= 10e-9
                          and 0 < fall['propagation_delay_s'] <= 10e-9,
    )
    return dict(format='dac-monitor-t200-class-check-v1',
                qualification='isolated SN74H00-class test of live T200 functional model; cross-reference is type-family evidence, not a production T200 spread or native-stage qualification',
                sources=dict(robotron='reference/k7222-11/pc1715-ic-crossref.json',
                             ti='https://ftpmirror.your.org/pub/misc/bitsavers/components/ti/_dataBooks/1985_TI_The_TTL_Data_Book_Vol_2.pdf',
                             ti_printed_pages='3-3, 3-6'),
                model_sha256=hashlib.sha256(MODEL.read_bytes()).hexdigest(),
                bounds_sha256=hashlib.sha256(Path(signal_path.__file__).read_bytes()).hexdigest(),
                dc_logic=logic, vil_limit=vil, vih_limit=vih,
                unloaded_high=high_unloaded, loaded_high=high, loaded_low=low,
                high_input_bias=high_bias, low_input_bias=low_bias,
                switching_load=dict(resistance_ohm=280, capacitance_f=25e-12),
                rising_output=rise, falling_output=fall,
                checks=checks, passed=all(checks.values()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f"T200 functional model: {sum(report['checks'].values())}/{len(report['checks'])} class checks pass")
    raise SystemExit(0 if report['passed'] else 2)
