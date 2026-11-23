"""Compare the live SSY20A neck model with the SSY20 data-sheet DC biases.

The printed SSY20A suffix is provisionally mapped to data-sheet group A.
This checks gain and saturation only; a separate conditional switching screen
checks timing, while fT and connected stress remain open.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT/'profiles/k7222-11-neck.json'
MODELS = ROOT/'circuits/k7222-11-neck-models.cir'
VALUE = re.compile(r'(i\(vce\)|i\(vcc\)|v\(c\)|v\(b\))\s*=\s*([-+\d.eE]+)')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def op(parameters, source, probes):
    deck = ('SSY20A source-model bias check\n.temp 25\n'
            + ''.join(f'.param {key}={value}\n' for key, value in parameters.items())
            + MODELS.read_text() + '\n' + source
            + 'Q1 c b 0 SSY20A_BOUND\n.control\nop\nprint '
            + ' '.join(probes) + '\n.endc\n.end\n')
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)/'bias.cir'
        path.write_text(deck)
        result = subprocess.run(['ngspice', '-n', '-b', str(path)],
                                capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('ngspice bias check failed: '+result.stdout[-500:]+result.stderr[-500:])
    values = {key: float(value) for key, value in VALUE.findall(result.stdout)}
    if set(probes) != set(values):
        raise RuntimeError('ngspice omitted requested bias values: '+result.stdout[-500:])
    return values


def run():
    profile = json.loads(PROFILE.read_text())
    parameter_specs = profile['parameters']
    nominal = {key: spec['nominal'] for key, spec in parameter_specs.items()}
    cases = {}
    for label, bf in (('minimum', parameter_specs['q_bf']['minimum']),
                      ('nominal', parameter_specs['q_bf']['nominal']),
                      ('maximum', parameter_specs['q_bf']['maximum'])):
        parameters = dict(nominal, q_bf=bf)
        low, high = .005, .05
        for _ in range(24):
            base_current = (low+high)/2
            point = op(parameters,
                       f'VCE c 0 1.3\nIBASE 0 b {base_current}\n',
                       ('i(vce)', 'v(c)', 'v(b)'))
            if -point['i(vce)'] > .5:
                high = base_current
            else:
                low = base_current
        base_current = (low+high)/2
        gain = op(parameters, f'VCE c 0 1.3\nIBASE 0 b {base_current}\n',
                  ('i(vce)', 'v(c)', 'v(b)'))
        sat = op(parameters,
                 'VCC vcc 0 40\nRLOAD vcc c 80\nIBASE 0 b 0.05\n',
                 ('i(vcc)', 'v(c)', 'v(b)'))
        cases[label] = {
            'spice_BF': bf,
            'gain_bias': {'collector_voltage_v': gain['v(c)'],
                          'collector_current_a': -gain['i(vce)'],
                          'base_current_a': base_current,
                          'h21E': -gain['i(vce)']/base_current},
            'saturation_bias': {'collector_voltage_v': sat['v(c)'],
                                'collector_current_a': -sat['i(vcc)'],
                                'base_current_a': .05},
            'gain_in_group_A_range': 18 <= -gain['i(vce)']/base_current <= 35,
            'saturation_below_1_v': 0 <= sat['v(c)'] <= 1,
        }
    joint_gain_corners = []
    for bf in (parameter_specs['q_bf']['minimum'],
               parameter_specs['q_bf']['maximum']):
        for ikf in (parameter_specs['q_ikf']['minimum'],
                    parameter_specs['q_ikf']['maximum']):
            parameters = dict(nominal, q_bf=bf, q_ikf=ikf)
            low, high = .005, .05
            for _ in range(24):
                base_current = (low+high)/2
                point = op(parameters,
                           f'VCE c 0 1.3\nIBASE 0 b {base_current}\n',
                           ('i(vce)', 'v(c)', 'v(b)'))
                if -point['i(vce)'] > .5:
                    high = base_current
                else:
                    low = base_current
            base_current = (low+high)/2
            gain = op(parameters,
                      f'VCE c 0 1.3\nIBASE 0 b {base_current}\n',
                      ('i(vce)', 'v(c)', 'v(b)'))
            effective_gain = -gain['i(vce)']/base_current
            joint_gain_corners.append({
                'BF': bf, 'IKF_a': ikf, 'h21E': effective_gain,
                'within_group_A': 18 <= effective_gain <= 35,
            })
    worst_series = dict(nominal,
                        q_bf=parameter_specs['q_bf']['minimum'],
                        q_ikf=parameter_specs['q_ikf']['minimum'],
                        **{key: parameter_specs[key]['maximum']
                           for key in ('q_rb', 'q_rc', 'q_re')})
    worst_sat = op(worst_series,
                   'VCC vcc 0 40\nRLOAD vcc c 80\nIBASE 0 b 0.05\n',
                   ('i(vcc)', 'v(c)', 'v(b)'))
    return {'format': 'dac-monitor-ssy20-model-dc-check-v1',
            'qualification': 'DC bias comparison only; group-A suffix mapping and fT/switching remain unverified',
            'source': 'https://www.tiffe.de/robotron/Bausteinuebersicht/DDR-Halbleiter.pdf',
            'profile_sha256': sha(PROFILE), 'models_sha256': sha(MODELS),
            'data_sheet_conditions': {
                'gain': 'IC=500 mA, VCE=1.3 V, h21E group A 18..35',
                'saturation': 'IC=500 mA, IB=50 mA, VCEsat <=1 V'},
            'cases': cases,
            'joint_bf_ikf_gain_corners': joint_gain_corners,
            'high_series_resistance_saturation': {
                'q_rb_ohm': worst_series['q_rb'],
                'q_rc_ohm': worst_series['q_rc'],
                'q_re_ohm': worst_series['q_re'],
                'collector_voltage_v': worst_sat['v(c)'],
                'collector_current_a': -worst_sat['i(vcc)'],
                'below_1_v': 0 <= worst_sat['v(c)'] <= 1,
            }}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    for label, case in report['cases'].items():
        print(label, 'h21E', round(case['gain_bias']['h21E'], 2),
              'VCEsat', round(case['saturation_bias']['collector_voltage_v'], 3), 'V')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
