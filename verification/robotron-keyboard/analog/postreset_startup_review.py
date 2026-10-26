#!/usr/bin/env python3
"""Review unchanged post-reset controls without conflating fix effects with convergence."""
import argparse
import json
from pathlib import Path
from audit_log import complete, equal, records
from compare_firmware_io import sha as logical_sha
from postreset_startup_capture import MODES, validate_source
from raw_pair_review import compare_raw
from ttl7406_probe import sha

END = 0.00116
FIRMWARE = ('FIRST_FETCH ', 'BUS_', 'SERIAL_')


def validate_receipt(receipt, baseline, inputs, mode, runtime, build, source_digest):
    if not receipt.get('completed') or receipt.get('error') or receipt.get('timedOut') or receipt.get('exitCode') != 0:
        raise ValueError('Incomplete producer')
    if receipt['mode'] != mode or receipt['inputs'] != inputs:
        raise ValueError('Mismatched mode or inputs')
    expected = dict(baseline['environment'], **MODES[mode], ROBOTRON_HISTORY_STATE='off')
    if receipt['environment'] != expected:
        raise ValueError('Mismatched experimental conditions')
    if receipt['runtime'] != runtime or receipt['candidateBuildSha256'] != build:
        raise ValueError('Mismatched candidate runtime')
    if receipt['sourceRunSha256'] != source_digest or receipt['externalDependencies'] != baseline['externalDependencies']:
        raise ValueError('Mismatched source or dependencies')
    if receipt['runnerSha256'] != sha(Path(__file__).with_name('postreset_startup_capture.py')):
        raise ValueError('Changed capture runner')
    if set(receipt['storage']) != {'waveform.raw'}:
        raise ValueError('Missing complete raw waveform')


def inspect_log(path, mode):
    summary = complete(path)
    if not summary['latchesMatch']:
        raise ValueError('Firmware latch mismatch')
    faults = summary['faults']
    if len(faults) != (1 if mode == 'retry' else 0):
        raise ValueError('Unexpected retry count')
    if faults and 'kind=newton ' not in faults[0]['record']:
        raise ValueError('Wrong retry kind')
    initialized = list(records(path, ('HISTORY_INIT ',)))
    expected = [] if mode in ('baseline', 'off') else ['HISTORY_INIT seed=none initialized=1 ports=69']
    if initialized != expected:
        raise ValueError('Missing or unexpected history initialization')
    counts = {}; last_edge = None
    for line in records(path, FIRMWARE):
        kind = line.split()[0]
        counts[kind] = counts.get(kind, 0) + 1
        if kind == 'BUS_EDGE_PS':
            last_edge = int(line.split()[1])
    if not counts.get('FIRST_FETCH') or last_edge is None or last_edge <= 1_000_001_000:
        raise ValueError('Missing post-reset firmware execution')
    summary['firmwareCounts'] = counts
    summary['lastBusEdgePs'] = last_edge
    return summary


def assess(source, off, combined, retry=None):
    baseline, inputs = validate_source(source)
    folders = {'off': off, 'combined': combined}
    if retry is not None:
        folders['retry'] = retry
    receipts = {m: json.loads((p / 'run.json').read_text()) for m, p in folders.items()}
    control = receipts['off']; scans = {}
    if control['runtime']['executable'] != baseline['runtime']['executable']:
        raise ValueError('Changed executable relative to baseline')
    for mode, folder in folders.items():
        receipt = receipts[mode]
        validate_receipt(receipt, baseline, inputs, mode, control['runtime'],
                         control['candidateBuildSha256'], sha(source / 'run.json'))
        for name, digest in inputs.items():
            if sha(folder / name) != digest:
                raise ValueError('Changed retained input')
        if logical_sha(folder / 'waveform.raw') != receipt['storage']['waveform.raw']['sha256']:
            raise ValueError('Changed retained waveform')
        if logical_sha(folder / 'ngspice.log') != receipt['logSha256']:
            raise ValueError('Changed retained log')
        scans[mode] = inspect_log(folder / 'ngspice.log', mode)
    if logical_sha(source / 'waveform.raw') != baseline['storage']['waveform.raw']['sha256']:
        raise ValueError('Changed baseline waveform')
    scans['baseline'] = inspect_log(source / 'ngspice.log', 'baseline')
    comparisons = {
        'disabledBaseline': compare_raw(off / 'waveform.raw', source / 'waveform.raw',
            [scans['off']['count'], scans['baseline']['count']], END, exact=True),
        'fixEffect': compare_raw(off / 'waveform.raw', combined / 'waveform.raw',
            [scans['off']['count'], scans['combined']['count']], END),
    }
    firmware = {'disabledBaseline': equal(off / 'ngspice.log', source / 'ngspice.log', FIRMWARE),
                'fixEffect': equal(off / 'ngspice.log', combined / 'ngspice.log', FIRMWARE)}
    if retry is not None:
        comparisons['forcedRetry'] = compare_raw(combined / 'waveform.raw', retry / 'waveform.raw',
            [scans['combined']['count'], scans['retry']['count']], END)
        firmware['forcedRetry'] = equal(combined / 'ngspice.log', retry / 'ngspice.log', FIRMWARE)
    return {'completed': True, 'qualified': False, 'comparisons': comparisons,
            'firmwareRecordsExactlyEqual': firmware, 'logs': scans,
            'receipts': {m: sha(p / 'run.json') for m, p in folders.items()},
            'sourceRunSha256': sha(source / 'run.json'), 'reviewerSha256': sha(Path(__file__)),
            'scope': 'Whole 1.16-ms post-reset window. Disabled baseline must match exactly; enabled differences are measured, not waived.',
            'notEstablished': ['Three-level numerical convergence', 'Private internal-state rollback',
                               'Startup and supply recovery', 'Full-repeat qualification', 'Device/load admission']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'off', 'combined', 'out'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--retry', type=Path)
    a = p.parse_args()
    result = assess(a.source, a.off, a.combined, a.retry)
    with a.out.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
