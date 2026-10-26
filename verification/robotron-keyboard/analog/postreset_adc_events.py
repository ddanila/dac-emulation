#!/usr/bin/env python3
"""Extract complete output events and bus-edge context from reviewed ADC logs."""
import argparse
from collections import deque
import json
from pathlib import Path
from audit_log import records
from postreset_startup_review import FIRMWARE
from ttl7406_probe import sha


def extract(lines, centers=()):
    recent = deque(maxlen=8)
    outputs, firmware, contexts = [], [], []
    pending = []
    windows = [{'centerSeconds': t, 'records': []} for t in centers]
    for line in lines:
        if line.startswith('TIME_AUDIT '):
            fields = dict(x.split('=', 1) for x in line.split()[2:])
            target = float(fields['target'])
            for window in windows:
                if abs(target - window['centerSeconds']) <= 2e-9:
                    window['records'].append(line)
        if line.startswith(FIRMWARE):
            firmware.append(line)
        if line.startswith('TIME_AUDIT output '):
            fields = dict(x.split('=', 1) for x in line.split()[2:])
            if set(fields) != {'actual', 'target', 'base', 'port'}:
                raise ValueError('Unexpected output event fields')
            outputs.append(fields)
        if line.startswith(('TIME_AUDIT ', 'BUS_')):
            for context in pending:
                context['following'].append(line)
            pending = [c for c in pending if len(c['following']) < 8]
            if line.startswith('BUS_EDGE_PS '):
                context = {'edge': line, 'preceding': list(recent), 'following': []}
                contexts.append(context)
                pending.append(context)
            recent.append(line)
    return {'outputs': outputs, 'firmware': firmware, 'busContexts': contexts,
            'targetWindows': windows}


def run(retained, out):
    retention = json.loads((retained / 'retention.json').read_text())
    out.mkdir(exist_ok=False)
    results = {}
    differences = json.loads((retained / 'firmware-differences.json').read_text())
    centers = [int(d['baseline'].split()[1]) * 1e-12 for d in differences['differences']
               if d['baseline'].startswith('BUS_EDGE_PS ')]
    for name, capture in retention['captures'].items():
        source = Path(capture['directory']) / 'ngspice.log.xz'
        expected = capture['outputs']['ngspice.log.xz']
        if source.stat().st_size != expected['bytes'] or sha(source) != expected['sha256']:
            raise ValueError('Changed complete source log')
        data = extract(records(source.with_suffix(''), ('TIME_AUDIT ',) + FIRMWARE), centers)
        if data['firmware'] != (retained / name / 'firmware.log').read_text().splitlines():
            raise ValueError('Changed firmware stream')
        if sha(source) != expected['sha256']:
            raise ValueError('Source changed during extraction')
        data['sourceCompressedSha256'] = expected['sha256']
        (out / (name + '.json')).write_text(json.dumps(data, indent=2) + '\n')
        results[name] = data
    pairs = {}
    for left, right in [('baseline', '25'), ('25', '12.5'), ('12.5', '6.25')]:
        a, b = results[left]['outputs'], results[right]['outputs']
        same = [x['port'] for x in a] == [x['port'] for x in b]
        pairs[left + '-' + right] = {
            'samePortSequence': same, 'counts': [len(a), len(b)],
            'changedActualTimes': [{'ordinal': i, 'left': x, 'right': y}
                                   for i, (x, y) in enumerate(zip(a, b))
                                   if x['actual'] != y['actual']] if same else None,
        }
    result = {'qualified': False, 'assessmentSha256': sha(retained / 'assessment.json'),
              'scope': 'Complete logged output-event sequence and adjacent bus timing context. '
                       'Output values and input threshold events are not present in TIME_AUDIT; '
                       'this cannot establish their equality or a causal defect. '
                       'BUS stdout and TIME_AUDIT stderr can be buffered independently: '
                       'adjacency is file order, not a causal timeline. Target windows use '
                       'the explicit TIME_AUDIT timestamps.', 'pairs': pairs}
    (out / 'assessment.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--retained', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    run(a.retained, a.out)
