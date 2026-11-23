"""Assess corrected connected T3 signs against the registered TP17 guideline."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
SCREEN = REF / 't3-upper-bridge-sign-screen.json'
TARGETS = REF / 'service-observations.json'
OUTPUT = REF / 't3-upper-bridge-tp17-assessment.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    screen, targets = json.loads(SCREEN.read_text()), json.loads(TARGETS.read_text())
    if screen['format'] != 'dac-monitor-t3-upper-bridge-sign-screen-v1':
        raise ValueError('wrong corrected connected sign screen')
    target = next(row for row in targets['waveforms'] if row['test_point'] == 17)
    if (target['model_node'] != 'h_sync' or target['approximate_swing_v'] != 80
            or target['acceptance_tolerance'] != .2):
        raise ValueError('TP17 target or mapping changed')
    nominal = target['approximate_swing_v']
    lo, hi = nominal * (1 - target['acceptance_tolerance']), nominal * (1 + target['acceptance_tolerance'])
    rows = []
    for case in screen['cases']:
        if case['status'] != 'complete':
            raise ValueError('TP17 assessment needs completed cases')
        low, high = case['observed']['tp17_mapped_v']
        swing = high - low
        rows.append(dict(candidate_id=case['candidate_id'], polarity=case['polarity'],
                         tp17_range_v=[low, high], tp17_swing_v=swing,
                         within_registered_band=lo <= swing <= hi))
    accepted = [row['candidate_id'] for row in rows if row['within_registered_band']]
    passed = (len(rows) == 8 and len(accepted) == 4 and
              all(row['polarity']['lower_taps'] == 1 for row in rows
                  if row['within_registered_band']))
    return dict(format='dac-monitor-t3-upper-bridge-tp17-assessment-v1',
                qualification='conditional amplitude comparison of final 1 ms connected startup; no EO2 bandwidth/probe correction, periodic state, installed winding or A5 sign qualification',
                screen_sha256=sha(SCREEN), target_register_sha256=sha(TARGETS),
                script_sha256=sha(Path(__file__)), target=dict(test_point=17,
                model_node='h_sync', nominal_vpp=nominal, tolerance_fraction=target['acceptance_tolerance'],
                band_vpp=[lo, hi], source=target['source']),
                cases=rows, conditional_tp17_compatible_ids=accepted,
                qualified_lower_tap_sign=None, a5_qualified=False, passed=passed)


if __name__ == '__main__':
    report = run()
    OUTPUT.write_text(json.dumps(report, indent=2) + '\n')
    print(f"{len(report['conditional_tp17_compatible_ids'])}/8 within TP17 amplitude band; passed={report['passed']}")
    raise SystemExit(0 if report['passed'] else 2)
