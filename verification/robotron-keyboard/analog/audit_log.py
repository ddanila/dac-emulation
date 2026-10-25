"""Bounded-memory validation and exact comparisons of complete audit logs."""
from itertools import zip_longest
import re
from filter_truncation_log import diagnostic
from trace_io import open_text

AUDIT = ('ROLLBACK_AUDIT ', 'TIME_AUDIT ')
BUS = ('BUS_EDGE_PS ', 'BUS_SAMPLE ', 'BUS_LATCH ')


def records(path, prefixes=None):
    with open_text(path) as stream:
        for line in stream:
            if prefixes is None:
                yield line
            else:
                line = line.strip()
                if line.startswith(prefixes):
                    yield line


def equal(left, right, prefixes=None):
    """Compare records exactly, including extra records at either endpoint."""
    sentinel = object()
    a, b = records(left, prefixes), records(right, prefixes)
    try:
        return all(x == y for x, y in zip_longest(a, b, fillvalue=sentinel))
    finally:
        a.close(); b.close()


def scan(path):
    counts = []; faults = []; pending = None
    bus_counts = [0, 0, 0]; last_edge = -1; latches_match = True
    failure = None; sorry = False; advances = 0
    for raw in records(path):
        line = raw.strip()
        failure = failure or diagnostic(raw)
        sorry = sorry or 'SORRY:' in raw
        if line.startswith('TIME_AUDIT advance '): advances += 1
        if pending is not None and line.startswith(AUDIT):
            faults[pending]['following'] = line
            pending = None
        if line.startswith('ROLLBACK_FAULT '):
            if len(faults) >= 2:
                raise ValueError('Unexpected number of injected retries')
            faults.append({'record': line, 'following': None}); pending = len(faults)-1
        matches = re.findall(r'No\. of Data Rows\s*:\s*(\d+)', raw)
        counts.extend(map(int, matches))
        if len(counts) > 1: raise ValueError('Missing unique completion count')
        if line.startswith(BUS[0]):
            match = re.fullmatch(r'BUS_EDGE_PS (\d+)', line)
            if not match or int(match[1]) <= last_edge:
                raise ValueError('Malformed or nonmonotonic bus edge')
            last_edge = int(match[1]); bus_counts[0] += 1
        elif line.startswith(BUS[1]):
            if len(line.split()) != 7: raise ValueError('Malformed bus observation')
            bus_counts[1] += 1
        elif line.startswith(BUS[2]):
            fields = line.split()
            if len(fields) != 4: raise ValueError('Malformed bus observation')
            latches_match &= bool(fields[2].lower() == fields[3].lower() and re.fullmatch('[0-9a-fA-F]{2}', fields[3]))
            bus_counts[2] += 1
    return {'count': counts[0] if counts else None, 'faults': faults,
            'busCounts': bus_counts, 'latchesMatch': latches_match,
            'diagnostic': failure, 'sorry': sorry, 'advances': advances}


def complete(path):
    result = scan(path)
    if result['diagnostic'] or result['sorry']: raise ValueError('Solver/HDL diagnostic')
    if result['count'] is None: raise ValueError('Missing unique completion count')
    a, b, c = result['busCounts']
    if not a or a != b or b != c: raise ValueError('Missing bus observations')
    return result
