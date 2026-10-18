#!/usr/bin/env python3
"""Compare a declared host-voltage prefix of a failed replay; never qualification."""
import argparse
import json
import math
from pathlib import Path

from host_waveform_comparison import compare_samples, rows
from compare_firmware_io import sha


def prefix(samples, end):
    """Keep every source knot through end, interpolating only the final boundary."""
    if not math.isfinite(end) or end <= 0:
        raise ValueError('Expected a positive finite prefix end')
    previous = None
    for row in samples:
        if row[0] <= end:
            yield row
            if row[0] == end:
                return
        else:
            if previous is None:
                raise ValueError('Prefix begins outside capture')
            fraction = (end-previous[0])/(row[0]-previous[0])
            yield (end, *(a+fraction*(b-a) for a,b in zip(previous[1:],row[1:])))
            return
        previous = row
    raise ValueError('Prefix ends outside capture')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('replay', type=Path)
    parser.add_argument('--end-seconds', required=True, type=float)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    reports = [json.loads((p/'report.json').read_text()) for p in (args.source,args.replay)]
    if reports[1]['sourceReportSha256'] != sha(args.source/'report.json'):
        raise ValueError('Replay belongs to a different source report')
    signals = None
    inputs = []
    for path, report in zip((args.source,args.replay),reports):
        trace = path/'host-trace.txt'
        identities = report.get('originalWaveformIdentities', report['artifacts'])
        if sha(trace) != identities['host-trace.txt']:
            raise ValueError('Host capture hash differs')
        with trace.open() as stream:
            header = stream.readline().split()
        if header[0] != 'time' or not all(s.startswith('v(') for s in header[1:]):
            raise ValueError('Expected voltage observations')
        if signals is not None and header[1:] != signals:
            raise ValueError('Host observation nodes differ')
        signals = header[1:]
        # Validate the entire captured ordering even outside the selected prefix.
        samples = list(rows(trace,signals,float('inf')))
        inputs.append(list(prefix(samples,args.end_seconds)))
    result = compare_samples(*inputs)
    for signal, entry in zip(signals,result['signals']):
        entry['signal'] = signal
    report = {'qualified':False,'scope':__doc__, 'comparison':result,
              'boundary':'Absolute-time sampled linear interpolation only. Explicitly bounded diagnostic prefix of incomplete runs, not a convergence or physical accuracy pass. Aborted-capture states are not specimen observations.',
              'sourceReportSha256':sha(args.source/'report.json'),
              'replayReportSha256':sha(args.replay/'report.json'),
              'sources':{name:sha(Path(__file__).parent/name) for name in
                         ('compare_driver_replay.py','host_waveform_comparison.py')}}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2)+'\n')
    print(args.out)


if __name__ == '__main__':
    main()
