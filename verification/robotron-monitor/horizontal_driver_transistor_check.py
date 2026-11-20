"""Compare the live V13 driver model with the historical SF126–129 family.

The printed suffix is SF1280; the available data book specifies the base
SF128 family but does not explain that suffix. The checks therefore establish
a class comparator, not an exact part identity or an inductive switching test.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
REGISTER = ROOT/'reference/k7222-11/device-model-register.json'
MODELS = ROOT/'circuits/k7222-11-horizontal-models.cir'
SHEET = ROOT/'circuits/k7222-11-horizontal-oscillator.kicad_sch'
SOURCE = 'https://www.tiffe.de/Robotron/Bausteinuebersicht/DDR-Halbleiter.pdf'
MODEL = 'HOR_DRIVER_N'
SOURCE_ID = '012-6921:V13'
VALUE = re.compile(r'(i\(vce\)|v\(c\)|v\(b\))\s*=\s*([-+\d.eE]+)')
AC_GAIN = re.compile(r'mag\(i\(vce\)\)\s*=\s*([-+\d.eE]+)')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def simulate(stimulus, analysis, probes, model=MODEL, models_path=None):
    models_path = MODELS if models_path is None else models_path
    deck = ('Horizontal transistor class check\n.temp 25\n'
            + models_path.read_text() + '\nQ1 c b 0 ' + model + '\n'
            + stimulus + '\n.control\nset noaskquit\n' + analysis
            + '\nprint ' + ' '.join(probes) + '\n.endc\n.end\n')
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)/'check.cir'
        path.write_text(deck)
        result = subprocess.run(['ngspice', '-n', '-b', str(path)],
                                capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('ngspice transistor check failed: '
                           + result.stdout[-500:] + result.stderr[-500:])
    return result.stdout


def op(stimulus, probes, model=MODEL, models_path=None):
    output = simulate(stimulus, 'op', probes, model, models_path)
    values = {key: float(value) for key, value in VALUE.findall(output)}
    if set(values) != set(probes):
        raise RuntimeError('ngspice omitted transistor operating-point values: '
                           + output[-500:])
    return values


def gain_at(target_a, vce_v, model=MODEL, models_path=None):
    low, high = 1e-8, .02
    for _ in range(25):
        base_a = (low+high)/2
        point = op(f'VCE c 0 {vce_v}\nIBASE 0 b {base_a:.12g}',
                   ('i(vce)', 'v(b)'), model, models_path)
        if -point['i(vce)'] > target_a:
            high = base_a
        else:
            low = base_a
    base_a = (low+high)/2
    point = op(f'VCE c 0 {vce_v}\nIBASE 0 b {base_a:.12g}',
               ('i(vce)', 'v(b)'), model, models_path)
    collector_a = -point['i(vce)']
    return dict(collector_current_a=collector_a, base_current_a=base_a,
                collector_emitter_voltage_v=vce_v,
                base_emitter_voltage_v=point['v(b)'], hFE=collector_a/base_a)


def ac_gain_at(base_a, vce_v, frequency_hz, model=MODEL, models_path=None):
    output = simulate(f'VCE c 0 {vce_v}\nIBASE 0 b DC {base_a:.12g} AC 1',
                      f'ac lin 1 {frequency_hz:.12g} {frequency_hz:.12g}',
                      ('mag(i(vce))',), model, models_path)
    match = AC_GAIN.search(output)
    if not match:
        raise RuntimeError('ngspice omitted current-gain row: '
                           + output[-500:])
    return float(match.group(1))


def ac_gain_at_15mhz(base_a):
    return ac_gain_at(base_a, 10, 15e6)


def active_model():
    with tempfile.TemporaryDirectory() as directory:
        xml = Path(directory)/'oscillator.xml'
        subprocess.run(['kicad-cli', 'sch', 'export', 'netlist',
                        '--format', 'kicadxml', '-o', str(xml), str(SHEET)],
                       check=True, capture_output=True, text=True)
        root = ET.parse(xml).getroot()
    rows = []
    for comp in root.findall('./components/comp'):
        source_id = next((field.text for field in comp.findall('./fields/field')
                          if field.get('name') == 'SourceId'), None)
        if source_id == SOURCE_ID:
            rows.append((comp.get('ref'), comp.findtext('value')))
    if len(rows) != 1 or rows[0][1] != MODEL:
        raise ValueError('V13 KiCad export does not select the tested model')
    return rows[0][0]


def run():
    register = json.loads(REGISTER.read_text())
    matches = [row for row in register['devices'] if row['id'] == SOURCE_ID]
    if len(matches) != 1 or matches[0]['model'] != MODEL:
        raise ValueError('V13 device register is missing or inconsistent')
    entry = matches[0]
    line = re.search(r'^\.model ' + MODEL + r' NPN\(([^)]*)\)',
                     MODELS.read_text(), re.M)
    if not line:
        raise ValueError('live V13 model declaration is absent')
    parameters = dict(re.findall(r'([A-Z]+)=([^\s]+)', line.group(1)))
    if set(parameters) != set(entry['parameters']):
        raise ValueError('V13 register does not cover every explicit model parameter')
    scales = {'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3}
    for key, token in parameters.items():
        scale = scales.get(token[-1], 1)
        numeric = float(token[:-1] if scale != 1 else token)*scale
        if not math.isclose(numeric, entry['parameters'][key]['nominal'], rel_tol=1e-10):
            raise ValueError('V13 register nominal differs from live '+key)
    gain = gain_at(.05, 2)
    ac_bias = gain_at(.01, 10)
    ac_gain = ac_gain_at_15mhz(ac_bias['base_current_a'])
    sat = op('ICLOAD 0 c .15\nIBASE 0 b .015', ('v(c)', 'v(b)'))
    targets = entry['comparison_targets']
    if (targets['hFE_50ma']['range'], targets['VCEsat_v']['maximum'],
            targets['fT_hz']['minimum']) != ([18, 1120], .5, 60e6):
        raise ValueError('V13 historical class targets changed without updating check')
    checks = dict(
        broad_family_gain=18 <= gain['hFE'] <= 1120
            and abs(gain['collector_current_a']-.05) < .0005,
        saturation_dc_proxy=0 <= sat['v(c)'] <= .5,
        transition_frequency_proxy=15e6*ac_gain >= 60e6
            and abs(ac_bias['collector_current_a']-.01) < .0001,
    )
    return dict(format='dac-monitor-v13-model-class-check-v1',
                qualification='SF128 family DC and 15 MHz AC class proxy; SF1280 suffix, '
                              'inductive storage/fall and connected stress remain open',
                source=SOURCE, model_file_sha256=sha(MODELS),
                register_sha256=sha(REGISTER), sheet_sha256=sha(SHEET),
                assembly_source_id=SOURCE_ID, assembly_reference=active_model(),
                explicit_model_parameters=parameters,
                data_book_targets=targets, gain_at_50ma=gain,
                saturation_dc_proxy=dict(collector_current_a=.15,
                                         base_current_a=.015,
                                         collector_emitter_voltage_v=sat['v(c)'],
                                         base_emitter_voltage_v=sat['v(b)']),
                ac_bias_at_10ma=ac_bias, ac_current_gain_at_15mhz=ac_gain,
                transition_frequency_proxy_hz=15e6*ac_gain,
                checks=checks, passed=all(checks.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"V13 hFE {report['gain_at_50ma']['hFE']:.1f}; "
          f"DC VCEsat {report['saturation_dc_proxy']['collector_emitter_voltage_v']:.3f} V; "
          f"15 MHz fT proxy {report['transition_frequency_proxy_hz']/1e6:.1f} MHz")
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
