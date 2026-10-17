#!/usr/bin/env python3
"""Independent Decimal matrix-exponential reference for the frozen linear fixture.

This is a diagnostic, not another board model. Identical serial branches permit
one branch current K; I is supply current, B board rail, U cable voltage relative
to host return G, H host source voltage. Return current is I-2K by KCL.
The reference assumes initially discharged capacitors and zero inductor current.
It covers only the first 100 ns of the source's linear ramp.
"""
import argparse
from decimal import Decimal as D, localcontext
import hashlib
import json
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / 'reports/supply-startup-isolation/linear.cir'
FIXTURE_SHA256 = 'f4bb958167fca8576d24c85e5631ae130c0c80a1127cf20317181a3fa7608321'


def parameters(path=FIXTURE):
    if hashlib.sha256(path.read_bytes()).hexdigest() != FIXTURE_SHA256:
        raise ValueError('Reference derivation requires the frozen linear fixture')
    values = {}
    suffixes = {'u': D('1e-6'), 'n': D('1e-9'), 'p': D('1e-12'), 'k': D('1e3'), 't': D('1e12')}
    for line in path.read_text().splitlines()[1:]:
        words = line.split()
        if words and words[0][0] in 'RCL':
            value = words[3]
            values[words[0]] = D(value[:-1]) * suffixes[value[-1]] if value[-1] in suffixes else D(value)
    return values


def evaluate(seconds, precision=100):
    """Return voltages/current from exp(A*t), with no SPICE time stepping."""
    seconds = D(str(seconds))
    if not seconds.is_finite() or not 0 <= seconds <= D('1e-7'):
        raise ValueError('Reference time must be between zero and 100 ns')
    if precision < 60:
        raise ValueError('At least 60 decimal digits required for cancellation')
    with localcontext() as context:
        context.prec = precision
        p = parameters()
        cb = sum(v for k, v in p.items() if k.startswith(('C3.', 'C5.')))
        cl, rp, ro, rl = (p[k] for k in ('Cdata_load', 'R10.2', 'Rdata_off', 'Rdata_load'))
        ls, lr, lc = (p[k] for k in ('L1.3', 'L1.2', 'L1.4'))
        rs, rr, rc = (p[k] for k in ('RL1.3', 'RL1.2', 'RL1.4'))

        def nodes(state):
            b, u, i, k, h, constant = state
            s = (b - rp*k) / (1 + rp/ro)
            g = (-rr*(i-2*k) - lr/ls*(h-b-rs*i)
                 + 2*lr/lc*(s-u-rc*k)) / (1+lr/ls+2*lr/lc)
            return s, g

        def derivative(state):
            b, u, i, k, h, constant = state
            s, g = nodes(state)
            return [(i-2*k-2*s/ro)/cb, (k-u/rl)/cl,
                    (h+g-b-rs*i)/ls, (s-g-u-rc*k)/lc,
                    D('5e6')*constant, D(0)]

        # Augmented homogeneous state includes H'=5e6 and constant'=0.
        term = [D(0)]*5 + [D(1)]
        total = term[:]
        for order in range(1, 2001):
            term = [v*seconds/order for v in derivative(term)]
            total = [a+b for a, b in zip(total, term)]
            if order > 100 and max(map(abs, term)) < D(10)**(-precision+10):
                break
        else:
            raise ArithmeticError('Matrix exponential series did not converge')
        _, g = nodes(total)
        return {'boardRailV': +total[0], 'cableReturnV': +g,
                'hostSourceCurrentA': -total[2], 'cableDifferentialV': +total[1],
                'serialBranchCurrentA': +total[3]}


def compare_trace(path, source_start_ns):
    """Compare raw reduced-fixture observations; offset comes from the source PWL.

    No inferred phase alignment or accuracy acceptance gate is applied here.
    The caller must ensure the trace uses the frozen fixture's electrical values.
    """
    start = D(str(source_start_ns))*D('1e-9')
    if not start.is_finite() or start < 0:
        raise ValueError('Source start must be finite and nonnegative')
    names = ('boardRailV', 'cableReturnV', 'hostSourceCurrentA')
    maxima = {name: {'absoluteDifference': D(0), 'timeSeconds': D(0)} for name in names}
    first = last = None
    count = 0
    with path.open() as stream:
        next(stream)
        for line in stream:
            row = [D(value) for value in line.split()]
            if len(row) != 4 or not all(value.is_finite() for value in row):
                raise ValueError('Invalid reduced-fixture waveform')
            time = row[0]
            if time < 0 or (last is not None and time < last):
                raise ValueError('Invalid waveform time')
            if first is None:
                first = time
            last = time
            reference = evaluate(max(D(0), time-start))
            for name, value in zip(names, row[1:]):
                difference = abs(value-reference[name])
                if difference > maxima[name]['absoluteDifference']:
                    maxima[name] = {'absoluteDifference': difference, 'timeSeconds': time}
            count += 1
    if first is None or first != 0:
        raise ValueError('Waveform must include the initial unpowered state')
    return {'scope': 'Reduced linear fixture only; differences, not a board qualification gate',
            'sourceStartNs': str(source_start_ns), 'firstSeconds': str(first),
            'lastSeconds': str(last), 'samples': count,
            'maximumDifferences': {name: {k: str(v) for k, v in item.items()}
                                   for name, item in maxima.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--times-ns', nargs='+', default=['0.01', '0.1', '1', '10', '99', '100'])
    parser.add_argument('--trace', type=Path, help='Raw time/board-rail/cable-return/host-current waveform of this fixture')
    parser.add_argument('--source-start-ns', default='0', help='Known source PWL start, never fitted to the waveform')
    args = parser.parse_args()
    result = {'scope': __doc__, 'fixtureSha256': FIXTURE_SHA256, 'samples': []}
    for ns in args.times_ns:
        time = D(ns)*D('1e-9')
        low, high = evaluate(time, 80), evaluate(time, 120)
        difference = max(abs(low[k]-high[k]) for k in low)
        if difference > D('1e-30'):
            raise ArithmeticError('Reference precision refinement failed')
        result['samples'].append({'timeSeconds': str(time),
                                  'values': {k: str(v) for k, v in high.items()},
                                  'precisionDifferenceMaximum': str(difference)})
    if args.trace:
        result['comparison'] = compare_trace(args.trace, args.source_start_ns)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
