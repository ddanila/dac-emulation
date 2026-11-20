"""Audit active V18 BJT parameters against BU508AF-class DC corner checks."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile

import horizontal_output_transistor_check as check


ROOT = Path(__file__).resolve().parent
REGISTER = ROOT/'reference/k7222-11/device-model-register.json'
CLASS = ROOT/'reference/k7222-11/class-typical-register.json'
MODEL = check.MODELS
DECLARATION = re.compile(r'^\.model HOR_OUTPUT_N NPN\(([^)]*)\)$', re.M)
PARAMETER = re.compile(r'([A-Z]+)=([^\s]+)')
SCALE = {'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def numeric(token):
    factor = SCALE.get(token[-1], 1)
    return float(token[:-1] if factor != 1 else token)*factor


def declaration(source):
    match = DECLARATION.search(source)
    if match is None:
        raise ValueError('active V18 model declaration missing')
    tokens = dict(PARAMETER.findall(match.group(1)))
    if len(tokens) != len(PARAMETER.findall(match.group(1))):
        raise ValueError('duplicate V18 model parameter')
    return match.group(0), {key: numeric(token) for key, token in tokens.items()}


def measured(model_text, original_line, parameters, folder):
    variant_line = '.model HOR_OUTPUT_N NPN(' + ' '.join(
        f'{key}={value:.12g}' for key, value in parameters.items()) + ')'
    path = folder/'variant.cir'
    path.write_text(model_text.replace(original_line, variant_line))
    previous = check.MODELS
    try:
        check.MODELS = path
        low = check.gain_at(.1)
        high = check.gain_at(4.5)
        vce = check.op('ICLOAD 0 c 4.5\nIBASE 0 b 1.6\n', ('v(c)', 'v(b)'))
        vbe = check.op('ICLOAD 0 c 4.5\nIBASE 0 b 2\n', ('v(c)', 'v(b)'))
    finally:
        check.MODELS = previous
    return {'hFE_0p1a': low['hFE'], 'hFE_4p5a': high['hFE'],
            'VCEsat_v': vce['v(c)'], 'VBEsat_v': vbe['v(b)']}


def run():
    register = json.loads(REGISTER.read_text())
    entry = next(item for item in register['devices'] if item['id'] == '012-6921:V18')
    text = MODEL.read_text()
    line, active = declaration(text)
    defined = entry['parameters']
    if set(active) != set(defined):
        raise ValueError('V18 register and active model parameter sets differ')
    for key, value in active.items():
        item = defined[key]
        if abs(value-item['nominal']) > 1e-10*max(abs(value), 1e-12):
            raise ValueError('V18 register nominal differs from active model: '+key)
        low, high = item['bounds']
        if not low <= value <= high:
            raise ValueError('V18 nominal outside its registered bounds: '+key)
    typical = json.loads(CLASS.read_text())
    fields = {item['id'].split('.')[-1]: item for item in typical['entries']
              if item['id'].startswith('012-6921:V18.')}
    if set(fields) != set(active):
        raise ValueError('A6 V18 entries do not cover every active parameter')
    for key, item in fields.items():
        if (not math.isclose(item['value'], active[key], rel_tol=1e-10)
                or item['bounds'] != defined[key]['bounds']):
            raise ValueError('A6 V18 value or bounds differ from active register: '+key)
    targets = entry['comparison_targets']
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        for bf in defined['BF']['bounds']:
            for ikf in defined['IKF']['bounds']:
                variant = dict(active, BF=bf, IKF=ikf)
                result = measured(text, line, variant, folder)
                rows.append({'BF': bf, 'IKF_a': ikf, **result})
        maximum = dict(active)
        maximum.update(BF=defined['BF']['bounds'][0],
                       IKF=defined['IKF']['bounds'][0],
                       RB=defined['RB']['bounds'][1],
                       RC=defined['RC']['bounds'][1],
                       RE=defined['RE']['bounds'][1])
        saturated = measured(text, line, maximum, folder)
    gain_pass = all(targets['hFE_0p1a']['minimum'] <= row['hFE_0p1a']
                    <= targets['hFE_0p1a']['maximum']
                    and row['hFE_4p5a'] >= targets['hFE_4p5a']['minimum']
                    for row in rows)
    saturation_pass = (saturated['VCEsat_v'] <= targets['VCEsat_v']['maximum']
                       and saturated['VBEsat_v'] <= targets['VBEsat_v']['maximum'])
    return {
        'format': 'dac-monitor-v18-bjt-bounds-v1',
        'qualification': '25 C BU508AF-class DC gain and saturation corner check for active V18; not original transistor identity, inductive switching, temperature, SOA or connected-stage qualification',
        'sources': [register['sources'][key]['url'] for key in entry['sources']],
        'source_hashes': {str(path.relative_to(ROOT)): sha(path)
                          for path in (MODEL, REGISTER, CLASS, Path(__file__),
                                       check.ROOT/'horizontal_output_transistor_check.py')},
        'active_parameters': active,
        'gain_corner_cases': rows,
        'maximum_series_resistance_case': {
            'BF': maximum['BF'], 'IKF_a': maximum['IKF'],
            'RB_ohm': maximum['RB'], 'RC_ohm': maximum['RC'],
            'RE_ohm': maximum['RE'], **saturated},
        'checks': {'gain_corners': gain_pass,
                   'saturation_resistance_corner': saturation_pass},
        'passed': gain_pass and saturation_pass,
        'remaining': ['The original V18 identity and fitted parasitics are unknown.',
                      'Joint capacitance, transit, temperature and connected stress bounds remain unqualified.',
                      'The active BJT has no reverse emitter-base breakdown or full safe-operating-area model.'],
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"V18 DC gain corners={len(report['gain_corner_cases'])}; "
          f"gain/saturation checks={report['checks']}")
    if not report['passed']:
        raise SystemExit(1)
