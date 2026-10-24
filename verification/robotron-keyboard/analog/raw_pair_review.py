"""Compare complete raw waveforms at absolute time with bounded memory."""
import math
from host_waveform_comparison import compare_samples
from live_raw_review import signal_name
from raw_waveform import header, rows
from trace_io import open_binary


def compare_raw(left, right, counts, expected_end, *, exact=False):
    if len(counts)!=2:
        raise ValueError('Need two complete sample counts')
    if not math.isfinite(expected_end) or expected_end <= 0:
        raise ValueError('Invalid required endpoint')
    with open_binary(left) as a, open_binary(right) as b:
        layouts = [header(stream) for stream in (a,b)]
        names = [[signal_name(n) for n in layout[0]] for layout in layouts]
        if any(len(set(n)) != len(n) for n in names) or set(names[0]) != set(names[1]):
            raise ValueError('Different or ambiguous observation scope')
        for (_, declared), count in zip(layouts, counts):
            if declared not in (0,count):
                raise ValueError('Header disagrees with complete log count')
        order = [names[1].index(n) for n in names[0]]
        def samples(stream, width, count, selection):
            first = last = None
            for row in rows(stream,width,count):
                if first is None:
                    first = row[0]
                    if first != 0:raise ValueError('Waveform must start at zero')
                last = row[0]
                yield tuple(row[i] for i in selection)
            if last is None or abs(last-expected_end)>2*math.ulp(expected_end):
                raise ValueError('Incomplete declared observation window')
        streams = [samples(a,len(names[0]),counts[0],range(len(names[0]))),
                   samples(b,len(names[1]),counts[1],order)]
        if exact:
            from itertools import zip_longest
            for index,(x,y) in enumerate(zip_longest(*streams)):
                if x != y:raise ValueError('Different raw sample at row '+str(index))
            return {'allSamplesExactlyEqual':True,'samples':counts[0],
                    'endSeconds':expected_end,'signals':names[0][1:]}
        result = compare_samples(*streams)
        result['signals'] = {name:{'unit':'A' if name.startswith('i(') or name.endswith('[i]') else 'V',
                                   'maximumAbsoluteDifference':value['maximumDifferenceV'],
                                   'timeSeconds':value['timeSeconds']}
                             for name,value in zip(names[0][1:],result['signals'])}
        result['maximumVoltageDifference'] = max(v['maximumAbsoluteDifference'] for v in result['signals'].values() if v['unit']=='V')
        result['boundary'] = 'All observed samples, piecewise-linear comparison on both absolute-time grids. No alignment or intersample extrema claim.'
        return result
