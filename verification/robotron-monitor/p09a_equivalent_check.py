"""Check the labelled P09A equivalent against an LM709C-class fixture."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

import reference

ROOT = Path(__file__).resolve().parent
MODEL = ROOT / 'devices/p09a-equivalent.cir'


def dc_case(vin, follower):
    model = MODEL.read_text()
    inverted = 'output' if follower else 'zero'
    source = '' if follower else 'Vzero zero 0 0\n'
    deck = f'''* P09A equivalent isolated class fixture
{model}
Vp vp 0 15
Vm vm 0 -15
Vi input 0 {vin}
{source}Xamp ca {inverted} input vm co raw vp cb P09A_EQUIV
C1 ca comp 5n
R1 comp cb 1.5k
C2 co raw 200p
R2 raw output 51
Rl output 0 2k
.control
op
print v(output) i(Vp) i(Vm) i(Vi)
.endc
.end
'''
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'fixture.cir'
        path.write_text(deck)
        result = subprocess.run(['ngspice', '-b', str(path)],
                                capture_output=True, text=True, timeout=30)
    if result.returncode or re.search(r'error|warning|singular matrix',
                                      result.stdout + result.stderr, re.I):
        raise RuntimeError('P09A DC fixture failed: ' + result.stdout + result.stderr)
    values = {}
    for expression in ('v(output)', 'i(vp)', 'i(vm)', 'i(vi)'):
        match = re.search(r'^' + re.escape(expression) + r' = ([^\s]+)',
                          result.stdout, re.M)
        if not match:
            raise RuntimeError('missing fixture value ' + expression)
        values[expression] = float(match.group(1))
    return dict(input_v=vin, output_v=values['v(output)'],
                positive_supply_current_a=-values['i(vp)'],
                negative_supply_current_a=values['i(vm)'],
                positive_input_bias_a=-values['i(vi)'])


def transient(compensation_f):
    probes = [dict(expression=e) for e in ('v(input)', 'v(output)')]
    profile = dict(name='P09A equivalent compensated step',
                   subcircuits={'P09A_EQUIV': 8}, probes=probes)
    bench = f'''Vp vp 0 15
Vm vm 0 -15
Vi input 0 PULSE(-1 1 10u 1n 1n 40u 80u)
Xamp ca output input vm co raw vp cb P09A_EQUIV
C1 ca comp {compensation_f}
R1 comp cb 1.5k
C2 co raw 200p
R2 raw output 51
Rl output 0 2k
'''
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)
        (path / 'run.cir').write_text(reference.deck(
            profile, [], {}, 0, 30e-6, 1e-8, MODEL.read_text(), bench))
        result = subprocess.run(['ngspice', '-b', 'run.cir'], cwd=path,
                                capture_output=True, text=True, timeout=30)
        if result.returncode or re.search(r'error|warning|timestep too small',
                                          result.stdout + result.stderr, re.I):
            raise RuntimeError('P09A transient fixture failed: ' + result.stdout + result.stderr)
        rows = reference.read_samples(path / 'samples.txt', probes, 0, 30e-6, 1e-8)
    crossing = next(row[0] for row in rows if row[0] > 10e-6 and row[2] > .8)
    slopes = [(b[2] - a[2]) / (b[0] - a[0]) for a, b in zip(rows, rows[1:])
              if 10.01e-6 <= a[0] <= 20e-6]
    return dict(input_compensation_f=compensation_f,
                output_0p8v_crossing_s=crossing,
                maximum_post_step_slew_v_per_s=max(slopes))


def run():
    follower = [dc_case(vin, True) for vin in (-10, -8, -1, 0, 1, 8, 10)]
    open_loop = {str(vin): dc_case(vin, False) for vin in (-.01, -1e-6, 0, 1e-6, .01)}
    nominal = transient(5e-9)
    heavier = transient(20e-9)
    gain = (open_loop['1e-06']['output_v'] - open_loop['-1e-06']['output_v']) / 2e-6
    checks = dict(
        follower_tracks=all(abs(row['output_v'] - row['input_v']) < .05 for row in follower),
        output_swing=all(abs(open_loop[str(v)]['output_v']) >= 10 for v in (-.01, .01)),
        gain=gain >= 15000,
        quiescent_current=.001 <= follower[3]['positive_supply_current_a'] <= .0066,
        input_bias=0 <= follower[3]['positive_input_bias_a'] <= 1.5e-6,
        slew=.125e6 <= nominal['maximum_post_step_slew_v_per_s'] <= .5e6,
        compensation_slows=heavier['output_0p8v_crossing_s']
                            > nominal['output_0p8v_crossing_s'] + 1e-6,
        rail_current_balance=all(abs(row['positive_supply_current_a']
                                     - row['negative_supply_current_a']
                                     - row['output_v'] / 2000) < 2e-6 for row in follower),
    )
    return dict(format='dac-monitor-p09a-equivalent-class-check-v1',
                qualification='isolated LM709C-class comparison of a labelled functional equivalent; not P09A identification or connected-stage qualification',
                source=dict(url='https://media.digikey.com/pdf/Data%20Sheets/Texas%20Instruments%20PDFs/LM709.pdf',
                            manufacturer='National Semiconductor / Texas Instruments',
                            document='LM709 Operational Amplifier, SNOS659A',
                            limits='LM709C: 15 V/mV minimum gain, +/-10 V minimum output swing at 2 kohm, 6.6 mA maximum standby, 1.5 uA maximum input bias; 0.25 V/us typical slew and 150 ohm typical output resistance'),
                model_sha256=hashlib.sha256(MODEL.read_bytes()).hexdigest(),
                setup=dict(rails_v=[-15, 15], load_ohm=2000,
                           input_compensation_f=5e-9, input_compensation_ohm=1500,
                           output_compensation_f=200e-12, output_series_ohm=51),
                follower=follower, open_loop=open_loop,
                open_loop_small_signal_gain=gain,
                transient_nominal=nominal, transient_heavier_compensation=heavier,
                checks=checks, passed=all(checks.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run()
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"P09A equivalent: {sum(result['checks'].values())}/{len(result['checks'])} "
          'isolated class checks pass')
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
