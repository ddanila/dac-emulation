"""Exact local corrections to logged constant-capacitor matrix/RHS additions."""
from collections import defaultdict
from fractions import Fraction as F
import math


def fields(line):
    return dict(item.split('=', 1) for item in line.split()[2:])


def parse(text):
    group, pending, latest = None, None, None
    result = {}
    for line in text.splitlines():
        if line.startswith('CAP_AUDIT begin '):
            if group is not None:
                raise ValueError('Nested capacitor load')
            f = fields(line)
            group = {'time': float.fromhex(f['time']), 'delta': float.fromhex(f['delta']),
                     'order': int(f['order']), 'capacitors': []}
            if not math.isfinite(group['time']) or not math.isfinite(group['delta']) or group['delta'] <= 0:
                raise ValueError('Invalid capacitor trial')
        elif line.startswith('CAP_AUDIT before '):
            if group is None or pending is not None:
                raise ValueError('Unpaired capacitor before record')
            f = fields(line)
            pending = {k: v if k == 'name' else int(v) if k in ('p', 'n') else float.fromhex(v)
                       for k, v in f.items()}
        elif line.startswith('CAP_AUDIT after '):
            f = fields(line)
            if pending is None or f['name'] != pending['name']:
                raise ValueError('Unpaired capacitor after record')
            after = {k: float.fromhex(v) for k,v in f.items() if k != 'name'}
            group['capacitors'].append({'before': pending, 'after': after})
            pending = None
        elif line == 'CAP_AUDIT end':
            if group is None or pending is not None or not group['capacitors']:
                raise ValueError('Incomplete capacitor load')
            latest, group = group, None
        elif line.startswith('LINEAR_AUDIT begin '):
            f = fields(line)
            if latest is None or (latest['time'], latest['delta'], latest['order']) != (
                    float.fromhex(f['time']), float.fromhex(f['delta']), int(f['order'])):
                raise ValueError('Linear system has no matching capacitor load')
            identity = int(f['id'])
            if identity in result:
                raise ValueError('Duplicate linear system')
            result[identity], latest = latest, None
    if group is not None or pending is not None or not result:
        raise ValueError('Missing or incomplete capacitor audit')
    return result


def corrections(group):
    """Return exact additive corrections, keeping all other assembled terms fixed."""
    if group['order'] not in (1, 2):
        raise ValueError('Only trapezoidal orders 1/2 admitted')
    matrix, rhs, observations = defaultdict(F), defaultdict(F), []
    names = set()
    for item in group['capacitors']:
        before, after = item['before'], item['after']
        name, p, n = before['name'], before['p'], before['n']
        if name in names or p == n or min(p, n) < 0:
            raise ValueError('Ambiguous capacitor identity or endpoints')
        names.add(name)
        if (not all(math.isfinite(v) for k,v in before.items() if k != 'name')
                or not all(map(math.isfinite, after.values()))
                or before['m'] <= 0 or before['C'] <= 0):
            raise ValueError('Invalid capacitor values')
        m = F(before['m'])
        exact_g = m*F(before['ag0'])*F(before['C'])
        history = (F(before['ag1'])*F(before['q1']) if group['order'] == 1 else
                   -F(before['ag1'])*F(before['i1'])-F(before['ag0'])*F(before['q1']))
        exact_b = m*history
        changes, additions = [], []
        for key, row, col, sign in [('pp', p, p, 1), ('nn', n, n, 1),
                                     ('pn', p, n, -1), ('np', n, p, -1)]:
            if row == 0 or col == 0:
                continue  # Ground pointers are not matrix unknowns.
            observed = F(after[key])-F(before[key])
            correction = sign*exact_g-observed
            matrix[row,col] += correction
            changes.append(abs(correction))
            additions.append(abs(observed-sign*m*F(before['geq'])))
        rhs_changes = []
        for key, row, sign in [('bp', p, -1), ('bn', n, 1)]:
            if row == 0:
                continue
            correction = sign*exact_b-(F(after[key])-F(before[key]))
            rhs[row] += correction
            rhs_changes.append(abs(correction))
        observations.append({'name': name, 'positiveNode': p, 'negativeNode': n,
                             'maximumMatrixCorrectionSiemens': float(max(changes, default=F(0))),
                             'maximumAdditionDiscrepancySiemens': float(max(additions, default=F(0))),
                             'maximumRhsCorrectionAmps': float(max(rhs_changes, default=F(0)))})
    return dict(matrix), dict(rhs), observations
