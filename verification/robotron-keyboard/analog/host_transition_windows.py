#!/usr/bin/env python3
"""Retain exact producer samples around the largest host voltage differences."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from compare_firmware_io import sha
from trace_io import open_binary


def extract(path, signals, centers, radius, expected_sha):
    windows = [{'centerSeconds':center,'startSeconds':center-radius,
                'endSeconds':center+radius,'rows':[]} for center in sorted(set(centers))]
    if not windows or not math.isfinite(radius) or radius <= 0 or any(not math.isfinite(c) or c < radius for c in centers):
        raise ValueError('Invalid extraction windows')
    digest = hashlib.sha256()
    previous = None
    with open_binary(path) as stream:
        header = stream.readline()
        digest.update(header)
        if header.decode().split() != ['time',*signals]:
            raise ValueError('Unexpected host waveform header')
        for line in stream:
            digest.update(line)
            values = list(map(float,line.split()))
            if len(values) != len(signals)+1 or not all(map(math.isfinite,values)):
                raise ValueError('Invalid waveform row')
            t = values[0]
            if previous is not None and t <= previous[0]:
                raise ValueError('Non-increasing waveform time')
            for w in windows:
                if t >= w['startSeconds'] and not w['rows']:
                    if previous is None:
                        raise ValueError('Missing leading bracket')
                    w['rows'].append(previous)
                if w['rows'] and w['rows'][-1][0] <= w['endSeconds']:
                    w['rows'].append((t,line))
            previous = (t,line)
    if digest.hexdigest() != expected_sha:
        raise ValueError('Host waveform hash differs from producer report')
    for w in windows:
        if not w['rows'] or w['rows'][-1][0] <= w['endSeconds']:
            raise ValueError('Missing trailing bracket')
    return header,windows


def crossings(raw_rows, column, level=1.4):
    samples = [tuple(map(float,row[1].split())) for row in raw_rows]
    result = []
    for a,b in zip(samples,samples[1:]):
        if a[column] < level <= b[column] or a[column] >= level > b[column]:
            result.append({'timeSeconds':a[0]+(level-a[column])*(b[0]-a[0])/(b[column]-a[column]),
                           'direction':'rising' if b[column]>a[column] else 'falling'})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('comparison',type=Path)
    p.add_argument('coarse',type=Path)
    p.add_argument('fine',type=Path)
    p.add_argument('--radius-ns',type=float,default=100)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    comparison=json.loads(args.comparison.read_text())
    if comparison.get('completed') is not True or comparison.get('qualified') is not False:
        raise ValueError('Requires completed experimental voltage comparison')
    centers=[r['timeSeconds'] for r in comparison['observation']['signals']]
    captures=[]
    for name,directory in [('coarse',args.coarse),('fine',args.fine)]:
        if sha(directory/'report.json') != comparison['reports'][name]:
            raise ValueError('Producer report differs from comparison')
        producer=json.loads((directory/'report.json').read_text())
        header,windows=extract(directory/'host-trace.txt',producer['hostTraceSignals'],centers,
                               args.radius_ns*1e-9,producer['hostTraceSha256'])
        captures.append((name,header,windows))
    args.out.mkdir(parents=True,exist_ok=False)
    report={'qualified':False,'scope':__doc__,'comparisonSha256':sha(args.comparison),
            'sources':{name:sha(Path(__file__).with_name(name)) for name in
                       ('host_transition_windows.py','trace_io.py','compare_firmware_io.py')},
            'radiusNs':args.radius_ns,'crossingBoundary':'Linear interpolation at an illustrative 1.4 V threshold; not a measured switching threshold. Crossings include retained bracketing samples.', 'captures':[]}
    for name,header,windows in captures:
        for index,w in enumerate(windows):
            filename=f'{name}-{index}.txt'
            (args.out/filename).write_bytes(header+b''.join(row[1] for row in w['rows']))
            report['captures'].append({'run':name,'file':filename,'sha256':sha(args.out/filename),
                'centerSeconds':w['centerSeconds'],'requestedIntervalSeconds':[w['startSeconds'],w['endSeconds']],
                'retainedIntervalSeconds':[w['rows'][0][0],w['rows'][-1][0]],'rows':len(w['rows']),
                'bufferOutputCrossings':{label:crossings(w['rows'],col) for label,col in [('data',5),('clock',6)]}})
    (args.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(args.out/'report.json')


if __name__=='__main__':main()
