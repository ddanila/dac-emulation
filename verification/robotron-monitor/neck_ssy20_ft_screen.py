"""Measure neck SSY20A unity-current-gain frequency at the BSY34 comparator bias."""
import hashlib
import itertools
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile

import neck_transistor_check as dc

ROOT = Path(__file__).resolve().parent
PROFILE = dc.PROFILE
MODELS = dc.MODELS
REGISTER = ROOT/'reference/k7222-11/device-model-register.json'
OUTPUT = ROOT/'reference/k7222-11/ssy20-ft-corner-screen.json'
PARAMETERS = ('q_tf', 'q_cje', 'q_cjc')
BIAS_IC_A = .03
BIAS_VCE_V = 10
COMPARATOR_FT_HZ = 250e6


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def base_bias(parameters):
    low, high = 1e-5, .005
    for _ in range(26):
        base = (low + high)/2
        point = dc.op(parameters, f'VCE c 0 {BIAS_VCE_V}\nIBASE 0 b {base}\n',
                      ('i(vce)',))
        if -point['i(vce)'] > BIAS_IC_A:
            high = base
        else:
            low = base
    base = (low + high)/2
    point = dc.op(parameters, f'VCE c 0 {BIAS_VCE_V}\nIBASE 0 b {base}\n',
                  ('i(vce)',))
    if abs(-point['i(vce)'] - BIAS_IC_A) > 1e-6:
        raise ValueError('SSY20 AC bias did not reach 30 mA')
    return base, -point['i(vce)']


def measure(parameters, ngspice):
    base, collector = base_bias(parameters)
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        trace = folder/'gain.txt'
        deck = ('SSY20A current gain at 30 mA/10 V\n.temp 25\n'
                + ''.join(f'.param {key}={value}\n' for key, value in parameters.items())
                + MODELS.read_text()
                + f'\nVCE c 0 {BIAS_VCE_V}\nIBASE 0 b DC {base} AC 1\n'
                  'Q1 c b 0 SSY20A_BOUND\n.control\n'
                  'set wr_singlescale\nset wr_vecnames\n'
                  'ac dec 50 1Meg 10Gig\n'
                + f'wrdata {trace} mag(i(vce))\nquit\n.endc\n.end\n')
        path = folder/'ac.cir'
        path.write_text(deck)
        result = subprocess.run([str(ngspice), '-n', '-b', str(path)],
                                capture_output=True, text=True)
        if result.returncode or not trace.is_file():
            raise ValueError('SSY20 AC solve failed: '+(result.stdout+result.stderr)[-500:])
        rows = [tuple(map(float, line.split())) for line in trace.read_text().splitlines()[1:]]
    if len(rows) < 150 or rows[0][1] <= 1 or rows[-1][1] >= 1:
        raise ValueError('SSY20 unity-gain crossing not bracketed')
    crossings = [(left, right) for left, right in zip(rows, rows[1:])
                 if left[1] >= 1 > right[1]]
    if len(crossings) != 1:
        raise ValueError('SSY20 unity-gain crossing is ambiguous')
    left, right = crossings[0]
    fraction = -math.log(left[1])/(math.log(right[1])-math.log(left[1]))
    frequency = math.exp(math.log(left[0]) + fraction*(math.log(right[0])-math.log(left[0])))
    return dict(base_current_a=base, collector_current_a=collector,
                unity_gain_frequency_hz=frequency,
                meets_bsy34_comparator=frequency >= COMPARATOR_FT_HZ,
                crossing_bracket_hz=[left[0], right[0]])


def run():
    executable = shutil.which('ngspice')
    if executable is None:
        raise ValueError('ngspice executable not found')
    ngspice = Path(executable).resolve()
    specs = json.loads(PROFILE.read_text())['parameters']
    nominal = {key: spec['nominal'] for key, spec in specs.items()}
    register = json.loads(REGISTER.read_text())
    device = next(row for row in register['devices'] if row['id'] == '012-6891:V1')
    if device['comparison_targets']['fT_hz']['minimum'] != COMPARATOR_FT_HZ:
        raise ValueError('BSY34 comparison target changed')
    cases = []
    for bits in itertools.product((0, 1), repeat=len(PARAMETERS)):
        parameters = dict(nominal)
        for key, bit in zip(PARAMETERS, bits):
            parameters[key] = specs[key]['maximum'] if bit else specs[key]['minimum']
        cases.append(dict(corner={key: parameters[key] for key in PARAMETERS},
                          **measure(parameters, ngspice)))
    baseline = measure(nominal, ngspice)
    worst_cap = dict(nominal, q_cje=specs['q_cje']['maximum'],
                     q_cjc=specs['q_cjc']['maximum'])
    fast, slow = specs['q_tf']['minimum'], specs['q_tf']['maximum']
    for _ in range(16):
        middle = (fast + slow)/2
        worst_cap['q_tf'] = middle
        if measure(worst_cap, ngspice)['meets_bsy34_comparator']:
            fast = middle
        else:
            slow = middle
    worst_cap['q_tf'] = fast
    compatible = measure(worst_cap, ngspice)
    worst_cap['q_tf'] = slow
    incompatible = measure(worst_cap, ngspice)
    return dict(format='dac-monitor-ssy20-ft-corner-screen-v1',
                qualification='25 C short-circuit current-gain AC comparison at 30 mA/10 V; BSY34 is a period comparator, not a direct SSY20A fT specification',
                source_url='https://www.tiffe.de/robotron/Bausteinuebersicht/DDR-Halbleiter.pdf',
                profile_sha256=sha(PROFILE), models_sha256=sha(MODELS),
                register_sha256=sha(REGISTER), script_sha256=sha(__file__),
                ngspice_sha256=sha(ngspice),
                comparator=dict(type='BSY34', minimum_ft_hz=COMPARATOR_FT_HZ,
                                bias_ic_a=BIAS_IC_A, bias_vce_v=BIAS_VCE_V),
                nominal=baseline, cases=cases,
                bsy34_comparator_tf_boundary=dict(
                    condition='CJE and CJC at their active maxima; other parameters nominal',
                    last_compatible_tf_s=fast, first_incompatible_tf_s=slow,
                    compatible_ft_hz=compatible['unity_gain_frequency_hz'],
                    incompatible_ft_hz=incompatible['unity_gain_frequency_hz'],
                    candidate_only=True),
                all_corners_meet_comparator=all(row['meets_bsy34_comparator'] for row in cases),
                direct_ssy20_ft_qualified=False)


if __name__ == '__main__':
    report = run()
    OUTPUT.write_text(json.dumps(report, indent=2)+'\n')
    print('nominal fT MHz:', report['nominal']['unity_gain_frequency_hz']/1e6,
          'corner MHz:', [round(row['unity_gain_frequency_hz']/1e6, 1)
                         for row in report['cases']])
