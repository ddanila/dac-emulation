#!/usr/bin/env python3
"""Independently solve a recorded linear system; this does not rerun Newton iteration."""
import argparse
from decimal import Decimal, localcontext
from fractions import Fraction
import json
from pathlib import Path

from analog_driver_replay import sha
from linear_system_review import parse, review


def solve(system, precision):
    with localcontext() as context:
        context.prec = precision
        size = int(system['metadata']['size'])
        decimal = lambda value: Decimal(value.numerator)/Decimal(value.denominator)
        rows = [{size: decimal(system['b'][i+1])} for i in range(size)]
        for (i, j), value in system['a'].items():
            rows[i-1][j-1] = decimal(value)
        for k in range(size):
            pivot = max(range(k, size), key=lambda i: abs(rows[i].get(k, Decimal(0))))
            if not rows[pivot].get(k):
                raise ValueError('Singular recorded system at pivot '+str(k))
            rows[k], rows[pivot] = rows[pivot], rows[k]
            diagonal = rows[k][k]
            tail = [(j, value) for j, value in rows[k].items() if j > k]
            for i in range(k+1, size):
                entry = rows[i].pop(k, Decimal(0))
                if not entry:
                    continue
                factor = entry/diagonal
                for j, value in tail:
                    rows[i][j] = rows[i].get(j, Decimal(0)) - factor*value
        x = {}
        for i in range(size-1, -1, -1):
            x[i] = (rows[i].get(size, Decimal(0)) -
                    sum((value*x[j] for j, value in rows[i].items() if i < j < size), Decimal(0)))/rows[i][i]
        return {i+1: Fraction(value) for i, value in x.items()}


def decimal_text(value, precision):
    with localcontext() as context:
        context.prec = precision
        return str(Decimal(value.numerator)/Decimal(value.denominator))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--system-id', type=int, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    parent = json.loads((args.run/'report.json').read_text())
    if not parent.get('reproducedEvidence') or sha(args.run/'ngspice.log') != parent['artifacts']['ngspice.log']:
        raise ValueError('Expected verified, unchanged logged capture')
    systems, _ = parse((args.run/'ngspice.log').read_text())
    system = next(s for s in systems if s['id'] == args.system_id)
    result = {'qualified': False, 'scope': __doc__, 'sourceReportSha256': sha(args.run/'report.json'),
              'logSha256': parent['artifacts']['ngspice.log'], 'systemId': args.system_id,
              'sources': {name: sha(Path(__file__).parent/name) for name in
                          ('linear_precision_review.py', 'linear_system_review.py')},
              'original': review(system), 'solves': [],
              'boundary': 'Frozen stamped binary64 equations only. Increased arithmetic precision does not recover lost stamping precision, rerun nonlinear devices or integration, or establish physical qualification.'}
    previous = None
    for precision in (80, 160):
        solution = solve(system, precision)
        changed = dict(system, x=solution)
        checked = review(changed)
        differences = {i: abs(solution[i]-system['x'][i]) for i in solution}
        worst = max(differences, key=differences.get)
        result['solves'].append({'decimalPrecision': precision, 'residualReview': checked,
                                 'maximumChangeFromRecordedSolution': float(differences[worst]),
                                 'largestChangeNode': system['names'][worst],
                                 'maximumChangeFromPreviousPrecision': None if previous is None else
                                     float(max(abs(solution[i]-previous[i]) for i in solution)),
                                 'solution': {system['names'][i]: decimal_text(value, precision)
                                              for i, value in solution.items()}})
        previous = solution
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2)+'\n')
    print(args.out)


if __name__ == '__main__':
    main()
