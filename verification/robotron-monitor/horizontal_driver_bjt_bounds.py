"""Check selected V13 operating corners without assigning an unknown SF1280 group."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile

import horizontal_driver_transistor_check as check


ROOT = Path(__file__).resolve().parent
REGISTER = ROOT/'reference/k7222-11/device-model-register.json'
CLASS = ROOT/'reference/k7222-11/class-typical-register.json'
LINE = re.compile(r'^\.model HOR_DRIVER_N NPN\(([^)]*)\)$', re.M)
TOKEN = re.compile(r'([A-Z]+)=([^\s]+)')
SCALE = {'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def numeric(token):
    factor = SCALE.get(token[-1])
    return float(token[:-1])*factor if factor else float(token)


def measure(source, original, parameters, folder):
    model = '.model HOR_DRIVER_N NPN(' + ' '.join(
        f'{key}={value:.12g}' for key, value in parameters.items()) + ')'
    path = folder/'variant.cir'
    path.write_text(source.replace(original, model))
    gain = check.gain_at(.05, 2, models_path=path)
    bias = check.gain_at(.01, 10, models_path=path)
    ac = check.ac_gain_at(bias['base_current_a'], 10, 15e6, models_path=path)
    sat = check.op('ICLOAD 0 c .15\nIBASE 0 b .015', ('v(c)', 'v(b)'), models_path=path)
    return {'hFE_50ma': gain['hFE'], 'fT_proxy_hz': 15e6*ac,
            'VCEsat_v': sat['v(c)']}


def run():
    register = json.loads(REGISTER.read_text())
    device = next(row for row in register['devices'] if row['id'] == '012-6921:V13')
    source = check.MODELS.read_text()
    match = LINE.search(source)
    if match is None:
        raise ValueError('active V13 model declaration missing')
    tokens = TOKEN.findall(match.group(1))
    active = {key: numeric(value) for key, value in tokens}
    if len(active) != len(tokens) or set(active) != set(device['parameters']):
        raise ValueError('V13 active and registered parameter sets differ')
    typical = json.loads(CLASS.read_text())
    fields = {row['id'].split('.')[-1]: row for row in typical['entries']
              if row['id'].startswith('012-6921:V13.')}
    if set(fields) != set(active):
        raise ValueError('A6 V13 entries do not cover the active model')
    for key, value in active.items():
        item = device['parameters'][key]
        if (not math.isclose(value, item['nominal'], rel_tol=1e-10)
                or not item['bounds'][0] <= value <= item['bounds'][1]
                or not math.isclose(value, fields[key]['value'], rel_tol=1e-10)
                or item['bounds'] != fields[key]['bounds']):
            raise ValueError('V13 A2/A6/model disagreement: '+key)
    targets = device['comparison_targets']
    variants = [
        ('nominal', {}),
        ('low_ikf', {'IKF': device['parameters']['IKF']['bounds'][0]}),
        ('high_ikf', {'IKF': device['parameters']['IKF']['bounds'][1]}),
        ('upper_series_resistance', {key: device['parameters'][key]['bounds'][1]
                                     for key in ('RB', 'RC', 'RE')}),
        ('low_ikf_upper_series_resistance',
         {'IKF': device['parameters']['IKF']['bounds'][0],
          **{key: device['parameters'][key]['bounds'][1]
             for key in ('RB', 'RC', 'RE')}}),
    ]
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        cases = [{'name': name, 'overrides': overrides,
                  **measure(source, match.group(0), dict(active, **overrides), folder)}
                 for name, overrides in variants]
    passed = all(targets['hFE_50ma']['range'][0] <= row['hFE_50ma']
                 <= targets['hFE_50ma']['range'][1]
                 and row['fT_proxy_hz'] >= targets['fT_hz']['minimum']
                 and 0 <= row['VCEsat_v'] <= targets['VCEsat_v']['maximum']
                 for row in cases)
    return {
        'format': 'dac-monitor-v13-bjt-bounds-v1',
        'qualification': '25 C selected SF128-family DC and 15 MHz AC corners; not an SF1280 group identification, all joint corners, inductive switching, temperature or connected-stage qualification',
        'sources': [register['sources'][key]['url'] for key in device['sources']],
        'source_hashes': {str(path.relative_to(ROOT)): sha(path)
                          for path in (check.MODELS, REGISTER, CLASS, Path(__file__),
                                       ROOT/'horizontal_driver_transistor_check.py')},
        'active_parameters': active,
        'cases': cases,
        'selected_corners_pass': passed,
        'remaining': ['Printed SF1280 gain group and original current/voltage ratings are unresolved.',
                      'The broad family BF range is not an independently qualified joint corner with IKF.',
                      'Capacitance, transit, temperature, inductive storage/fall and connected stress remain unqualified.'],
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"V13 selected class corners={len(report['cases'])}; passed={report['selected_corners_pass']}")
    if not report['selected_corners_pass']:
        raise SystemExit(1)
