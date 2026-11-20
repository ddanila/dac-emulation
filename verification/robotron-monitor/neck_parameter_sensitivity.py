"""Bounded neck-stage sensitivity of the explicit SSY20A BJT parameters.

The neck bench has a synthetic input and ideal supplies. Its response is an
isolated-stage diagnostic, not connected CRT operation or an A2 freeze.
"""
import argparse
import hashlib
import json
from pathlib import Path

import reference


ROOT = Path(__file__).resolve().parent
PROFILE = ROOT/'profiles/k7222-11-neck.json'
MODEL = ROOT/'circuits/k7222-11-neck-models.cir'
STEP_S = 2e-7
STOP_S = 4e-4


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def summarize(run_directory, runtime):
    profile = reference.read_profile(PROFILE)
    specs = profile['parameters']
    cases = {
        'nominal': {},
        'low_gain': {'q_bf': specs['q_bf']['minimum'],
                     'q_ikf': specs['q_ikf']['minimum']},
        'high_gain': {'q_bf': specs['q_bf']['maximum'],
                      'q_ikf': specs['q_ikf']['maximum']},
        'high_series': {key: specs[key]['maximum']
                        for key in ('q_rb', 'q_rc', 'q_re')},
        'high_cap_slow_transit': {key: specs[key]['maximum']
                                  for key in ('q_cje', 'q_cjc', 'q_tf', 'q_tr')},
        'low_cap_fast_transit': {key: specs[key]['minimum']
                                 for key in ('q_cje', 'q_cjc', 'q_tf', 'q_tr')},
    }
    directory = Path(run_directory)
    directory.mkdir(parents=True, exist_ok=False)
    probes = [probe['name'] for probe in profile['probes']]
    selected = ('collector', 'cathode', 'intensity', 'grid1', 'grid2')
    rows = []
    nominal_samples = None
    for label, changes in cases.items():
        trial = directory/label
        report = reference.run(PROFILE, trial, stop=STOP_S,
                               step=STEP_S, changes=changes, runtime=runtime)
        samples = reference.read_samples(trial/'samples.txt', profile['probes'],
                                         0, STOP_S, STEP_S)
        if nominal_samples is None:
            nominal_samples = samples
        elif (len(samples) != len(nominal_samples) or
              any(abs(sample[0]-normal[0]) > 1e-12
                  for sample, normal in zip(samples, nominal_samples))):
            raise ValueError('case sample grids differ')
        late = [sample for sample in samples if sample[0] >= .0003]
        extrema = {name: {'min_v': min(sample[probes.index(name)+1]
                                       for sample in late),
                          'max_v': max(sample[probes.index(name)+1]
                                       for sample in late)}
                   for name in selected}
        difference = {name: max(abs(sample[probes.index(name)+1]-
                                    normal[probes.index(name)+1])
                                for sample, normal in zip(samples, nominal_samples)
                                if sample[0] >= .0003)
                      for name in selected}
        rows.append({'case': label, 'changes': changes,
                     'deck_sha256': report['hashes']['deck'],
                     'runtime_receipt_sha256': report['solver']['runtime_receipt_sha256'],
                     'samples_sha256': sha(trial/'samples.txt'),
                     'late_window_s': [.0003, STOP_S],
                     'late_extrema': extrema,
                     'late_max_abs_delta_from_nominal_v': difference})
    return {'format': 'dac-monitor-neck-bjt-sensitivity-v1',
            'qualification': 'isolated synthetic neck stage; exploratory joint corners, no connected stress or A2 completion',
            'source_hashes': {'producer': sha(ROOT/'neck_parameter_sensitivity.py'),
                              'reference': sha(ROOT/'reference.py'),
                              'profile': sha(PROFILE), 'model': sha(MODEL)},
            'runtime_path': str(Path(runtime)),
            'run_directory': str(directory),
            'time_step_s': STEP_S, 'stop_s': STOP_S,
            'cases': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-directory', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    a.output.write_text(json.dumps(summarize(a.run_directory, a.runtime),
                                   indent=2)+'\n')
