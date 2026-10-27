"""Compatible audit scanning with a conservative, source-pinned diagnostic prefilter.

Historical scanner files stay unchanged so retained evidence and live jobs keep
their original source identities. Every input line still reaches the scan loop.
"""
import hashlib,re
from pathlib import Path
import audit_log as legacy
from audit_log import records,equal,AUDIT,BUS
from filter_truncation_log import diagnostic as legacy_diagnostic
HERE=Path(__file__).resolve().parent
SUPPORTED_SOURCES={'audit_log.py': 'ca8415cd2cc6ab2b3dd55240beef16579e456ad33356c27234094beb8a9e3081', 'filter_truncation_log.py': 'd44c46ab976ff4a85f1016504a1338e82cc095396e0350c90e445132b6f23dc9', 'startup_truncation_log.py': '37501e7730864b5a060128a18936d21a0aa0ce34bca7d28cf95b71bf4945edb1', 'failure_evidence.py': 'd138491e9c32d452d6fbd498c06f131b4c23c53c84b6d6bc0b78c47e42d8cef8'}
SUPPORTED=all(hashlib.sha256((HERE/name).read_bytes()).hexdigest()==digest for name,digest in SUPPORTED_SOURCES.items())
# Every diagnostic alternative in the pinned sources contains one of these
# ASCII tokens. Non-ASCII input takes the original path, preserving re.I rules.
CANDIDATE_TOKENS=('warn','err','fail','fatal','singular','vlog','timestep','abort','xspice')


def diagnostic(text):
    if not SUPPORTED or not text.isascii():return legacy_diagnostic(text)
    lower=text.lower()
    if any(token in lower for token in CANDIDATE_TOKENS):return legacy_diagnostic(text)
    return None


def scan(path):
    if not SUPPORTED:return legacy.scan(path)
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
    if not SUPPORTED:return legacy.complete(path)
    result = scan(path)
    if result['diagnostic'] or result['sorry']: raise ValueError('Solver/HDL diagnostic')
    if result['count'] is None: raise ValueError('Missing unique completion count')
    a, b, c = result['busCounts']
    if not a or a != b or b != c: raise ValueError('Missing bus observations')
    return result
