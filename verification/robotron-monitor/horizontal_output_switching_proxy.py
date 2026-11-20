"""Measure V18 turn-off sensitivity in a declared current-fed clamp bench.

The bench holds 4.5 A into the collector, sets approximately 0.5 A forward
base current and switches toward -2.7 V through 4.5 uH at 16 kHz. Its ideal
collector current source and 200 V clamp do not reproduce ST Figure 9, so
the 10%-to-90% clamp transfer is not a data-sheet storage/fall-time score.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
MODELS = ROOT/'circuits/k7222-11-horizontal-models.cir'
SOURCE = 'https://www.st.com/resource/en/datasheet/bu508af.pdf'
OFF_S = 103.505e-6
CASES = {
    'low_tr': ('100n', '100n'),
    'nominal': ('100n', '500n'),
    'high_tr': ('100n', '2u'),
    'low_tf': ('50n', '500n'),
    'high_tf': ('200n', '500n'),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def model_variant(tf, tr):
    raw = MODELS.read_text()
    pattern = r'(?m)^\.model HOR_OUTPUT_N NPN\([^\n]+\)$'
    matches = re.findall(pattern, raw)
    if len(matches) != 1 or 'TF=100n TR=500n' not in matches[0]:
        raise ValueError('live V18 model declaration changed')
    changed = matches[0].replace('TF=100n TR=500n', f'TF={tf} TR={tr}')
    return raw.replace(matches[0], changed)


def deck(model, data):
    return ('''V18 current-fed turn-off sensitivity, not ST Figure 9
.temp 25
''' + model + '''
.model DPROXY D(IS=1n RS=.1 TT=1n)
Q1 c b 0 HOR_OUTPUT_N
ICOL 0 c 4.5
VSENSE c cl 0
DCLAMP cl clamp DPROXY
VCLAMP clamp 0 200
CSNUB c 0 1n
VDRIVE drive 0 PULSE(-2.7 1.225 1u 5n 5n 40u 62.5u)
RBASE drive lb 1
LBASE lb b 4.5u
VNEG neg 0 -2.7
DBASE neg b DPROXY
.control
set wr_singlescale
set wr_vecnames
tran 5n 110u 62u 1n
wrdata ''' + str(data) + ''' v(b) v(c) i(vsense) i(lbase)
.endc
.end
''')


def closest(rows, target):
    return min(rows, key=lambda row: abs(row[0]-target))


def rising_crossing(rows, threshold):
    for left, right in zip(rows, rows[1:]):
        if left[0] >= OFF_S and left[3] < threshold <= right[3]:
            return left[0] + (threshold-left[3])*(right[0]-left[0])/(right[3]-left[3])
    raise ValueError('clamp-current threshold never crossed after turn-off')


def run_case(label, tf, tr):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)/'proxy.cir'
        data = Path(directory)/'samples.dat'
        path.write_text(deck(model_variant(tf, tr), data))
        result = subprocess.run(['ngspice', '-n', '-b', str(path)],
                                capture_output=True, text=True)
        if result.returncode or not data.is_file():
            raise RuntimeError('V18 switching proxy failed: '+result.stdout[-500:]+result.stderr[-500:])
        with data.open() as stream:
            if next(stream).split() != ['time', 'v(b)', 'v(c)', 'i(vsense)', 'i(lbase)']:
                raise ValueError('unexpected switching proxy trace columns')
            rows = [[float(value) for value in line.split()] for line in stream]
    if not rows or any(len(row) != 5 for row in rows):
        raise ValueError('incomplete switching proxy trace')
    t10 = rising_crossing(rows, .45)
    t90 = rising_crossing(rows, 4.05)
    on = closest(rows, 100e-6)
    off = closest(rows, 109e-6)
    if not (.48 <= on[4] <= .52 and abs(off[3]-4.5) < .05
            and -3.5 <= off[1] <= -2.2 and OFF_S < t10 < t90 < 107e-6):
        raise ValueError('switching proxy bias or turn-off check failed')
    return dict(label=label, model_TF=tf, model_TR=tr,
                base_current_on_a=on[4], base_voltage_off_v=off[1],
                collector_voltage_on_v=on[2], collector_voltage_off_v=off[2],
                clamp_current_off_a=off[3],
                off_command_s=OFF_S, clamp_10_percent_s=t10,
                clamp_90_percent_s=t90,
                command_to_clamp_10_percent_s=t10-OFF_S,
                clamp_10_to_90_percent_s=t90-t10)


def run():
    cases = {name: run_case(name, tf, tr) for name, (tf, tr) in CASES.items()}
    nominal = cases['nominal']
    if not (cases['low_tf']['clamp_10_to_90_percent_s']
            < nominal['clamp_10_to_90_percent_s']
            < cases['high_tf']['clamp_10_to_90_percent_s']):
        raise ValueError('TF sweep did not bracket transfer interval')
    return dict(format='dac-monitor-v18-switching-proxy-v1',
                qualification='current-fed clamp diagnostic only; not ST inductive timing or an A2 pass',
                source=SOURCE, model_file_sha256=sha(MODELS),
                data_sheet_conditions=dict(collector_current_a=4.5,
                                           base_current_on_a=.5,
                                           base_voltage_off_v=-2.7,
                                           frequency_hz=16000,
                                           off_base_inductance_h=4.5e-6,
                                           typical_storage_s=2.5e-6,
                                           typical_fall_s=.2e-6),
                proxy_assumptions=['4.5 A ideal collector current source in place of the data-sheet inductive load',
                                   '200 V diode clamp and 1 nF collector snubber; neither value is specified by the data-sheet text',
                                   '1 ohm base-drive resistor and 1.225 V high drive chosen to produce approximately 0.5 A on current with the explicit V18 series resistances; 4.5 uH remains in series during both phases',
                                   'a diode to the -2.7 V rail limits reverse base-voltage overshoot from the base inductor',
                                   'first 10%-to-90% rise of clamp current is a transfer metric, not the data-sheet collector-current fall definition'],
                cases=cases, data_sheet_timing_verified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    nominal = report['cases']['nominal']
    print(f"V18 proxy command-to-10% {nominal['command_to_clamp_10_percent_s']*1e6:.3f} us; "
          f"clamp 10%-to-90% {nominal['clamp_10_to_90_percent_s']*1e6:.3f} us")


if __name__ == '__main__':
    main()
