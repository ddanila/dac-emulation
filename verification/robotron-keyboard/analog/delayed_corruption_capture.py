#!/usr/bin/env python3
"""Capture delayed-corruption controls in the retained 20-us observer fixture."""
import argparse
import json
from pathlib import Path
import output_history_capture as engine
from ttl7406_probe import sha

VARIANTS = {
    'off': {'ROBOTRON_HISTORY_STATE': 'off'},
    'check': {'ROBOTRON_HISTORY_STATE': 'check'},
    'immediate': {'ROBOTRON_HISTORY_STATE': 'corrupt', 'ROBOTRON_HISTORY_CORRUPT_AFTER': '0'},
    'delayed': {'ROBOTRON_HISTORY_STATE': 'corrupt', 'ROBOTRON_HISTORY_CORRUPT_AFTER': '0.00001'},
}
for environment in VARIANTS.values():
    environment.update(ROBOTRON_HISTORY_INIT='on', ROBOTRON_STAGED_OUTPUT='on')


def run(a):
    previous = engine.VARIANTS
    try:
        engine.VARIANTS = {a.mode: VARIANTS[a.mode]}
        engine.run(a.source, a.models, a.runtime, a.out)
    finally:
        engine.VARIANTS = previous
    path = a.out / a.mode / 'run.json'
    receipt = json.loads(path.read_text())
    receipt['variantControllerSha256'] = sha(Path(__file__))
    receipt['scope'] = '20-us observer qualification with reset at 1 us; not the full 1.16-ms post-reset control.'
    path.write_text(json.dumps(receipt, indent=2) + '\n')
    if receipt['exitCode'] != (2 if a.mode in ('immediate', 'delayed') else 0):
        raise ValueError('Unexpected producer exit')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'models', 'runtime', 'out'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--mode', choices=VARIANTS, required=True)
    run(p.parse_args())
