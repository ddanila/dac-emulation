"""Bound the centring-link choice in the existing TBY7 conditional stage."""

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
SYMMETRIC = REF / 't3-brimar-link-sensitivity.json'
ASYMMETRIC = REF / 't3-brimar-asymmetric-choke-screen.json'
OUTPUT = REF / 't3-centering-link-disposition.json'
LIMIT = .02


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_cases(path, asymmetric):
    report = json.loads(path.read_text())
    expected = ('dac-monitor-t3-brimar-asymmetric-choke-screen-v1' if asymmetric
                else 'dac-monitor-t3-brimar-link-sensitivity-v1')
    if report['format'] != expected:
        raise ValueError(f'unexpected source report format: {path}')
    fixed = report['fixed_conditions']
    if (fixed['feed_v'] != 42.50390625 or fixed['yoke_type'] != 'TBY7'
            or fixed['r4_position'] != .5 or fixed['max_step_ns'] != 50):
        raise ValueError(f'conditional stage settings changed: {path}')
    cases = {}
    for row in report['rows']:
        key = ((row['l1_h'], row['l2_h']) if asymmetric else
               (row['centering_coil_l_h'], row['centering_coil_l_h']))
        pair = row['link_pair']
        if pair not in ('E1+E2', 'E3+E4') or (key, pair) in cases:
            raise ValueError(f'link rows changed: {path}')
        observation = row['current_at_old_crossing'] if asymmetric else row
        cases[key, pair] = {
            'current_pp_a': observation['current_pp_a' if asymmetric else 'yoke_current_pp_a'],
            'eht_v': observation['eht_v' if asymmetric else 'eht_at_collector_peak_v'],
            'drive_peak_v': observation['drive_peak_v'],
        }
    if len(cases) != (4 if asymmetric else 6):
        raise ValueError(f'incomplete link-pair matrix: {path}')
    return cases


def run():
    rows = []
    for path, asymmetric in ((SYMMETRIC, False), (ASYMMETRIC, True)):
        cases = load_cases(path, asymmetric)
        for l1, l2 in sorted({key for key, _ in cases}):
            a, b = (cases[(l1, l2), pair] for pair in ('E1+E2', 'E3+E4'))
            changes = {name: abs(b[name] - a[name]) / abs(a[name])
                       for name in a}
            rows.append(dict(source_report=path.name, l1_h=l1, l2_h=l2,
                             default_pair='E1+E2', alternative_pair='E3+E4',
                             relative_change=changes))
    maximum = {name: max(row['relative_change'][name] for row in rows)
               for name in ('current_pp_a', 'eht_v', 'drive_peak_v')}
    if any(value >= LIMIT for value in maximum.values()):
        raise ValueError('link-pair effect exceeds 2% sensitivity budget')
    return dict(
        format='dac-monitor-t3-centering-link-disposition-v1',
        qualification='effect-bounded choice in one conditional prescribed-drive TBY7 stage; not installed-link identification, source-qualified L1/L2 behavior, TP17, or a connected native-frame result',
        input_sha256={path.name: sha(path) for path in (SYMMETRIC, ASYMMETRIC)},
        script_sha256=sha(Path(__file__)),
        sensitivity_limit_fraction=LIMIT,
        fixed_feed_v=42.50390625,
        comparisons=rows,
        maximum_relative_change=maximum,
        disposition='Keep E1+E2 as the explicit default and E3+E4 as a bounded model alternative for the conditional stage. Their measured current, sampled EHT and drive-peak effects are below the Phase A 2% sensitivity budget at all five screened choke assignments. The installed links remain unknown; this does not qualify T3 ratios or a native connected result.',
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(report['maximum_relative_change'])
