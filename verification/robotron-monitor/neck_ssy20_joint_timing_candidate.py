"""Screen one faster SSY20A proxy against switching and BSY34 AC comparisons."""
import hashlib
import itertools
import json
from pathlib import Path
import shutil
import tempfile

import neck_ssy20_ft_screen as ft
import neck_ssy20_switching_screen as switching

ROOT = Path(__file__).resolve().parent
PROFILE = switching.PROFILE
MODELS = switching.MODELS
OUTPUT = ROOT/'reference/k7222-11/ssy20-joint-timing-candidate.json'
CANDIDATE_TF = dict(nominal=4e-10, minimum=2e-10, maximum=5.3e-10)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run():
    executable = shutil.which('ngspice')
    if executable is None:
        raise ValueError('ngspice executable not found')
    ngspice = Path(executable).resolve()
    specs = json.loads(PROFILE.read_text())['parameters']
    model = MODELS.read_text()
    nominal = {key: value['nominal'] for key, value in specs.items()}
    if (specs['q_tf']['minimum'], specs['q_tf']['nominal'], specs['q_tf']['maximum']) != (
            2e-10, 2e-9, 3.2e-9):
        raise ValueError('active SSY20 timing profile changed')
    candidate_nominal = dict(nominal, q_tf=CANDIDATE_TF['nominal'])
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        active_switch = switching.solve(nominal, model, directory)
        candidate_switch = switching.solve(candidate_nominal, model, directory)
        cases = []
        for bits in itertools.product((0, 1), repeat=len(switching.DYNAMIC)):
            parameters = dict(candidate_nominal)
            for key, bit in zip(switching.DYNAMIC, bits):
                parameters[key] = (CANDIDATE_TF['maximum'] if key == 'q_tf' and bit
                                   else CANDIDATE_TF['minimum'] if key == 'q_tf'
                                   else specs[key]['maximum'] if bit else specs[key]['minimum'])
            cases.append(dict(corner={key: parameters[key] for key in switching.DYNAMIC},
                              **switching.solve(parameters, model, directory)))
    active_ac = ft.measure(nominal, ngspice)
    candidate_ac = ft.measure(candidate_nominal, ngspice)
    ac_cases = []
    for bits in itertools.product((0, 1), repeat=len(ft.PARAMETERS)):
        parameters = dict(candidate_nominal)
        for key, bit in zip(ft.PARAMETERS, bits):
            parameters[key] = (CANDIDATE_TF['maximum'] if key == 'q_tf' and bit
                               else CANDIDATE_TF['minimum'] if key == 'q_tf'
                               else specs[key]['maximum'] if bit else specs[key]['minimum'])
        ac_cases.append(dict(corner={key: parameters[key] for key in ft.PARAMETERS},
                             **ft.measure(parameters, ngspice)))
    passed = (candidate_switch['source_limits_met'] and len(cases) == 128
              and all(case['source_limits_met'] for case in cases)
              and candidate_ac['meets_bsy34_comparator']
              and len(ac_cases) == 8
              and all(case['meets_bsy34_comparator'] for case in ac_cases))
    return dict(format='dac-monitor-ssy20-joint-timing-candidate-v1',
                qualification='conditional faster SSY20A model envelope; SSY20 switching fixture thresholds inferred, BSY34 fT is a comparison only, connected stress untested',
                input_sha256={str(path.relative_to(ROOT)): sha(path)
                              for path in (PROFILE, MODELS, switching.SOURCE_READ,
                                           switching.OUTPUT, ft.OUTPUT,
                                           ROOT/'neck_ssy20_switching_screen.py',
                                           ROOT/'neck_ssy20_ft_screen.py', Path(__file__))},
                ngspice_sha256=sha(ngspice), candidate_tf_s=CANDIDATE_TF,
                active_nominal_switching=active_switch,
                candidate_nominal_switching=candidate_switch,
                switching_cases=cases,
                switching_worst_on_ns=max(case['on_ns'] for case in cases),
                switching_worst_off_ns=max(case['off_ns'] for case in cases),
                switching_failures=sum(not case['source_limits_met'] for case in cases),
                active_nominal_ac=active_ac, candidate_nominal_ac=candidate_ac,
                ac_cases=ac_cases,
                ac_worst_ft_hz=min(case['unity_gain_frequency_hz'] for case in ac_cases),
                ac_comparator_failures=sum(not case['meets_bsy34_comparator'] for case in ac_cases),
                bounds_promoted=False, connected_stress_checked=False,
                passed=passed)


if __name__ == '__main__':
    report = run()
    OUTPUT.write_text(json.dumps(report, indent=2)+'\n')
    print('joint candidate passed:', report['passed'], 'worst switching ns:',
          report['switching_worst_on_ns'], report['switching_worst_off_ns'],
          'worst AC MHz:', report['ac_worst_ft_hz']/1e6)
    raise SystemExit(0 if report['passed'] else 2)
