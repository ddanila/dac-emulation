"""Compare the live 1AD50_BOUND model with a 1N4148 signal-diode class.

The comparator does not identify the printed 1AD50 part. The result checks
the nominal model only; original ratings and bound sensitivity remain open.
"""
import argparse
import json
from pathlib import Path

import vertical_diode_check

ROOT = Path(__file__).resolve().parent
MODEL = ROOT/'circuits/k7222-11-neck-models.cir'
PROFILE = ROOT/'profiles/k7222-11-neck.json'


def run():
    result = vertical_diode_check.run(model_name='1AD50_BOUND',
                                      model_file=MODEL, profile_file=PROFILE,
                                      recovery_forward_source_v=1.639)
    result['format'] = 'dac-monitor-1ad50-class-model-check-v1'
    result['qualification'] = ('provisional 1N4148-class comparison; original '
                               '1AD50 identity and operating ratings remain open')
    result['unchecked'] = ['original 1AD50 identity and per-device voltage/current stress',
                           'joint-bound and native connected-frame response']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print('1AD50-class comparator checks:',
          'pass' if all(report['checked'].values()) else 'fail')
    return 0 if all(report['checked'].values()) else 2


if __name__ == '__main__':
    raise SystemExit(main())
