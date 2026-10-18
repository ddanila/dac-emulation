#!/usr/bin/env python3
"""Compare host voltages at absolute time using the union of retained sample knots."""
import argparse
import json
import math
from pathlib import Path
from compare_firmware_io import load_run, normalized_deck, compare, sha
from trace_io import open_text

HERE = Path(__file__).resolve().parent


def rows(path, signals, step_ns):
    with open_text(path) as stream:
        if stream.readline().split() != ['time', *signals]:
            raise ValueError('Host waveform header differs')
        previous = None
        for line in stream:
            row = tuple(map(float, line.split()))
            if len(row) != len(signals) + 1 or not all(map(math.isfinite, row)):
                raise ValueError('Invalid waveform row')
            if previous is None:
                if row[0] != 0:
                    raise ValueError('Waveform must start at zero')
            elif not 0 < row[0] - previous <= step_ns * 1e-9 + 1e-15:
                raise ValueError('Waveform time order or gap')
            previous = row[0]
            yield row


def compare_samples(coarse, fine):
    streams = [iter(coarse), iter(fine)]
    first = [next(s, None) for s in streams]
    if any(r is None for r in first) or first[0][0] != first[1][0]:
        raise ValueError('Missing or different waveform starts')
    width = len(first[0])
    if width < 2 or len(first[1]) != width:
        raise ValueError('Different waveform widths')
    previous = first[:]
    following = [next(s, None) for s in streams]
    if any(r is None for r in following):
        raise ValueError('Insufficient waveform samples')
    result = [{'maximumDifferenceV': abs(a-b), 'timeSeconds': first[0][0],
               'coarseV': a, 'fineV': b} for a,b in zip(first[0][1:],first[1][1:])]
    knots = 1
    last = first[0][0]
    while True:
        t = min(r[0] for r in following)
        values = []
        for a,b in zip(previous,following):
            if len(a) != width or len(b) != width or b[0] <= a[0]:
                raise ValueError('Invalid interpolation interval')
            fraction = (t-a[0])/(b[0]-a[0])
            values.append([x + fraction*(y-x) for x,y in zip(a[1:],b[1:])])
        for i,(a,b) in enumerate(zip(*values)):
            if abs(a-b) > result[i]['maximumDifferenceV']:
                result[i] = {'maximumDifferenceV':abs(a-b),'timeSeconds':t,'coarseV':a,'fineV':b}
        knots += 1
        last = t
        for i in range(2):
            if following[i][0] == t:
                previous[i] = following[i]
                following[i] = next(streams[i], None)
        if any(r is None for r in following):
            if not all(r is None for r in following):
                raise ValueError('Waveform extents differ')
            break
    return {'signals':result,'unionKnots':knots,'endSeconds':last}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('coarse',type=Path)
    parser.add_argument('fine',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    result = {'completed':False,'qualified':False,'scope':__doc__,
              'boundary':'Piecewise-linear sampled voltages only; no phase alignment or intersample peak claim. No physical accuracy tolerance is inferred.',
              'sources':{name:sha(HERE/name) for name in ('host_waveform_comparison.py','compare_firmware_io.py','trace_io.py','transient_analysis.py','serial_observation.py','led_observation.py','failure_evidence.py')}}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    try:
        coarse, ct = load_run(args.coarse)
        fine, ft = load_run(args.fine)
        if normalized_deck(args.coarse) != normalized_deck(args.fine):
            raise ValueError('Electrical decks differ beyond timestep')
        result['serialEdges'] = compare(coarse,fine,ct,ft,15,experimental_host=True)
        signals = coarse['hostTraceSignals']
        if len(signals) != 6 or signals != fine['hostTraceSignals']:
            raise ValueError('Host observation nodes differ')
        result['reports'] = {name:sha(path/'report.json') for name,path in [('coarse',args.coarse),('fine',args.fine)]}
        observation = compare_samples(rows(args.coarse/'host-trace.txt',signals,coarse['assumptions']['stepNs']),
                                      rows(args.fine/'host-trace.txt',signals,fine['assumptions']['stepNs']))
        import re
        duration = re.findall(r'^\.?tran [0-9.eE+-]+n ([0-9.eE+-]+)n$',(args.coarse/'io.cir').read_text(),re.M)
        if len(duration) != 1 or abs(observation['endSeconds']-float(duration[0])*1e-9)>1e-12:
            raise ValueError('Incomplete waveform extent')
        result['observation'] = observation
        for name, entry in zip(signals,observation['signals']):
            entry['signal'] = name
        result['completed'] = True
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(args.out)


if __name__ == '__main__':main()
