"""Inspect the horizontal drive chain in an unfinished connected raw trace."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct


PROBES = ('v(h_tank)', 'v(h_control)', 'v(h_base)', 'v(h_drivebase)',
          'v(h_drivecol)', 'v(h_outputbase)', 'v(h_col)', 'v(h_sync)',
          'v(h_hot)', 'i(lhorizontal)')
CROSSINGS = {'v(h_drivecol)': 10., 'v(h_hot)': 100.}


def summarize(path, window_s=.001):
    if not math.isfinite(window_s) or window_s <= 0:
        raise ValueError('window must be positive and finite')
    digest = hashlib.sha256()
    bins = []
    previous = None
    rows = 0
    trailing = 0
    with Path(path).open('rb') as stream:
        header = b''
        while not header.endswith(b'Binary:\n'):
            line = stream.readline()
            if not line or len(header) > 1_000_000:
                raise ValueError('missing ngspice raw header')
            digest.update(line)
            header += line
        text = header.decode()
        if 'Flags: real' not in text or 'Variables:\n' not in text:
            raise ValueError('expected real raw trace with variable table')
        count_match = re.search(r'No. Variables:\s+(\d+)', text)
        points_match = re.search(r'No. Points:\s+(\d+)', text)
        if count_match is None or points_match is None:
            raise ValueError('missing raw trace dimensions')
        count = int(count_match[1])
        names = re.findall(r'^\s*\d+\s+(\S+)\s+\S+\s*$',
                           text.split('Variables:\n')[1].split('Binary:')[0], re.M)
        if len(names) != count or names[0] != 'time' or any(p not in names for p in PROBES):
            raise ValueError('horizontal trace probes differ from expected names')
        indices = {name: names.index(name) for name in PROBES}
        unpack = struct.Struct('='+str(count)+'d')
        while data := stream.read(unpack.size):
            digest.update(data)
            if len(data) < unpack.size:
                trailing = len(data)
                break
            values = unpack.unpack(data)
            t = values[0]
            if not all(map(math.isfinite, values)) or t < 0 or (previous and t <= previous[0]):
                raise ValueError('invalid horizontal trace sample')
            slot = int(t/window_s)
            while len(bins) <= slot:
                bins.append({'start_s': len(bins)*window_s, 'samples': 0,
                             'minimum': {p: float('inf') for p in PROBES},
                             'maximum': {p: -float('inf') for p in PROBES},
                             'upcrossings': {p: 0 for p in CROSSINGS}})
            bucket = bins[slot]
            bucket['samples'] += 1
            for name, index in indices.items():
                value = values[index]
                bucket['minimum'][name] = min(bucket['minimum'][name], value)
                bucket['maximum'][name] = max(bucket['maximum'][name], value)
                if previous is not None and name in CROSSINGS:
                    if previous[1][name] < CROSSINGS[name] <= value:
                        bucket['upcrossings'][name] += 1
            previous = (t, {name: values[index] for name, index in indices.items()})
            rows += 1
    if rows < 2:
        raise ValueError('horizontal trace has fewer than two complete rows')
    return {'format': 'dac-monitor-native-grid-horizontal-chain-v1',
            'qualification': 'diagnostic-only from an unfinished connected raw trace; crossing counts are not a waveform score',
            'input_sha256': digest.hexdigest(), 'declared_points': int(points_match[1]),
            'complete_rows': rows, 'trailing_bytes': trailing,
            'last_time_s': previous[0], 'window_s': window_s,
            'crossing_thresholds': CROSSINGS, 'bins': bins}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = summarize(args.trace)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"{report['complete_rows']} rows through {report['last_time_s']:.6f} s; diagnostic only")
