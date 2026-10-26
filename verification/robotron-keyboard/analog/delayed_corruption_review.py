#!/usr/bin/env python3
"""Review immediate/delayed fault sensitivity with complete positive controls."""
import argparse
import json
import math
from pathlib import Path
import re
from audit_log import equal, records
from compare_firmware_io import sha as logical_sha
from delayed_corruption_capture import VARIANTS
from event_state_review import scheduling, check
from history_state_review import snapshots
from raw_pair_review import compare_raw
from staged_output_review import runtime_summary
from ttl7406_probe import sha


def fault(path, after, *, mutation_line="E_CORRUPT output-delay"):
    injections = []; rejected = []; fetches = []; mutation = 0; diagnostic = 0
    for line in records(path, ('HISTORY_CORRUPTION ', 'H_REJECT ', 'E_CORRUPT ', 'C_CORRUPT ', 'FIRST_FETCH ', 'Rejected trial')):
        if line.startswith('HISTORY_CORRUPTION '):
            match = re.fullmatch(r'HISTORY_CORRUPTION time=(\S+) after=(\S+)', line)
            if not match: raise ValueError('Malformed corruption marker')
            when, threshold = map(float, match.groups())
            if not all(map(math.isfinite, (when, threshold))) or threshold != after or when < after:
                raise ValueError('Early or mismatched corruption')
            injections.append(when)
        elif line.startswith('H_REJECT '):
            match = re.fullmatch(r'H_REJECT (\S+) equal=([01])', line)
            if not match or not math.isfinite(float(match[1])): raise ValueError('Malformed rejection')
            rejected.append((float(match[1]), int(match[2])))
        elif line == mutation_line: mutation += 1
        elif line.startswith('FIRST_FETCH '): fetches.append(int(line.split()[1]) * 1e-12)
        elif line == 'Rejected trial changed XSPICE history': diagnostic += 1
    if len(injections) != 1 or mutation != 1 or diagnostic != 1:
        raise ValueError('Missing unique detected corruption')
    when = injections[0]
    if not rejected or rejected[-1] != (when, 0) or any(equal != 1 or t >= when for t, equal in rejected[:-1]):
        raise ValueError('Corruption does not match final rejection')
    if after and (not rejected[:-1] or not any(t < when for t in fetches)):
        raise ValueError('Delayed control lacks prior rejection/firmware continuation')
    return {'detectedAtSeconds': when, 'requestedAfterSeconds': after,
            'earlierUnchangedRejections': len(rejected)-1, 'priorFirstFetch': any(t < when for t in fetches)}


def assess(root, baseline, *, fault_review=None, summary_review=None):
    summarize = summary_review or runtime_summary
    base = json.loads((baseline / 'run.json').read_text())
    runs = {m: json.loads((root / m / 'run.json').read_text()) for m in VARIANTS}
    positive = {}; negative = {}; histories = {}
    for mode, r in runs.items():
        expected_exit = 2 if mode in ('immediate', 'delayed') else 0
        if r['exitCode'] != expected_exit or r['inputs'] != base['inputs']:
            raise ValueError('Invalid capture or input mismatch')
        if r['runtime'] != runs['off']['runtime'] or r['candidateBuildSha256'] != sha(root / 'build.json'):
            raise ValueError('Different candidate conditions')
        if r['externalDependencies'] != base['externalDependencies'] or r['runtime']['executable'] != base['runtime']['executable']:
            raise ValueError('Changed external dependencies or executable')
        if r['environment'] != dict(base['environment'], **VARIANTS[mode]):
            raise ValueError('Different experimental environment')
        if r['variantControllerSha256'] != sha(Path(__file__).with_name('delayed_corruption_capture.py')) or r['sourceRunSha256'] != sha(baseline / 'run.json'):
            raise ValueError('Changed producer/source')
        for name, digest in r['inputs'].items():
            if sha(root / mode / name) != digest: raise ValueError('Changed retained input')
        for name, info in r['storage'].items():
            if logical_sha(root / mode / name) != info['sha256']: raise ValueError('Changed captured stream')
        log = root / mode / 'ngspice.log'
        if mode != 'off':
            stats = {}
            for _ in snapshots(log, stats, corrupt=expected_exit == 2): pass
            histories[mode] = stats
        if expected_exit == 2:
            negative[mode] = (fault_review or fault)(log, float(VARIANTS[mode]['ROBOTRON_HISTORY_CORRUPT_AFTER']))
        else:
            positive[mode] = summarize(log)
            if positive[mode]['count'] is None or positive[mode]['diagnostic'] or positive[mode]['sorry']:
                raise ValueError('Incomplete positive control')
    for name, info in base['storage'].items():
        if logical_sha(baseline / name) != info['sha256']: raise ValueError('Changed baseline stream')
    prior = summarize(baseline / 'ngspice.log')
    if base['exitCode'] != 0 or prior['count'] is None or prior['diagnostic'] or prior['sorry']:
        raise ValueError('Incomplete baseline')
    comparisons = {}
    for label, folder, count in [('disabledBaseline', baseline, prior['count']), ('enabledObserver', root / 'check', positive['check']['count'])]:
        comparisons[label] = compare_raw(root / 'off/waveform.raw', folder / 'waveform.raw',
            [positive['off']['count'], count], 20e-6, exact=True)
        if not equal(root / 'off/ngspice.log', folder / 'ngspice.log', ('FIRST_FETCH ', 'BUS_', 'SERIAL_')):
            raise ValueError('Changed positive firmware continuation')
    return {'completed': True, 'qualified': False, 'comparisons': comparisons, 'corruption': negative,
            'histories': histories, 'scheduling': scheduling(root / 'check/ngspice.log'),
            'receipts': {m: sha(root / m / 'run.json') for m in VARIANTS},
            'baselineReceiptSha256': sha(baseline / 'run.json'),
            'scope': 'Combined fixes in complete 20-us observer fixture. Delayed corruption follows firmware execution and unchanged rejected callbacks.',
            'notEstablished': ['Long post-reset internal-state qualification', 'Other-model and private HDL queues',
                               'Full startup/repeat/supply recovery', 'Numerical convergence', 'Device admission']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--baseline', type=Path)
    p.add_argument('--out', type=Path)
    p.add_argument('--check-manifest', action='store_true')
    a = p.parse_args()
    if a.check_manifest:
        check(a.root)
    else:
        if not a.baseline or not a.out: p.error('Need baseline and output')
        result = assess(a.root, a.baseline)
        with a.out.open('x') as f: json.dump(result, f, indent=2); f.write('\n')
