#!/usr/bin/env python3
"""Recompute logged ngspice divided differences with exact rational arithmetic."""
import argparse
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import json
import lzma
import math
from pathlib import Path
import re


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def divided_difference(values, deltas):
    """The CKTterr recurrence, preserving the supplied binary64 values exactly."""
    if len(values) != len(deltas) + 1 or not deltas or any(x <= 0 for x in deltas):
        raise ValueError('Invalid state history or timestep history')
    differences, intervals = list(values), list(deltas)
    for degree in range(len(deltas), 0, -1):
        differences = [(differences[i] - differences[i+1]) / intervals[i]
                       for i in range(degree)]
        intervals = [intervals[i+1] + deltas[i] for i in range(degree-1)]
    return differences[0]


def review_record(record, abstol, trtol):
    order = int(record['order'])
    if order not in (1, 2):
        raise ValueError('Only recorded trapezoidal orders 1 and 2 are supported')
    number = lambda key: float.fromhex(record[key])
    exact = lambda key: Fraction.from_float(number(key))
    difference = divided_difference([exact('q'+str(i)) for i in range(order+2)],
                                    [exact('dt'+str(i)) for i in range(order+1)])
    coefficient = Fraction.from_float((.5, .08333333333)[order-1])
    ratio = Fraction.from_float(trtol) * exact('tol') / max(Fraction.from_float(abstol), coefficient * abs(difference))
    with localcontext() as context:
        context.prec = 80
        proposal = Decimal(ratio.numerator) / Decimal(ratio.denominator)
        if order == 2:
            proposal = proposal.sqrt()
        proposal = float(proposal)
    logged = number('difference')
    relative = float(abs(Fraction.from_float(logged)-difference) / abs(difference)) if difference else abs(logged)
    logged_proposal = number('proposed')
    binary_difference = divided_difference([number('q'+str(i)) for i in range(order+2)],
                                          [number('dt'+str(i)) for i in range(order+1)])
    binary_proposal = trtol * number('tol') / max(abstol, float(coefficient)*abs(binary_difference))
    if order == 2:
        binary_proposal = math.sqrt(binary_proposal)
    if (not math.isclose(binary_difference, logged, rel_tol=1e-12, abs_tol=0)
            or not math.isclose(binary_proposal, logged_proposal, rel_tol=1e-12, abs_tol=0)):
        raise ValueError('Logged proposal does not match the declared recurrence/controls')
    jump = abs(exact('q0')-exact('q1'))
    ulp = max(math.ulp(number('q0')), math.ulp(number('q1')))
    return {'timeSeconds':number('time'), 'state':int(record['state']), 'order':order,
            'deltaSeconds':number('delta'), 'loggedProposalSeconds':logged_proposal,
            'exactHistoryProposalSeconds':proposal, 'differenceRelativeRoundingError':relative,
            'proposalRelativeRoundingError':abs(proposal-logged_proposal)/proposal,
            'stateJumpInLargerEndpointUlps':float(jump/Fraction.from_float(ulp)),
            'state0':number('q0'), 'state1':number('q1')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    assessment = json.loads((args.run/'assessment.json').read_text())
    for name, digest in assessment['retainedFilesSha256'].items():
        if sha(args.run/name) != digest:
            raise ValueError('Retained input differs: '+name)
    report = json.loads((args.run/'report.json').read_text())
    build = json.loads((args.run/'build-provenance.json').read_text())
    log = lzma.decompress((args.run/'ngspice.log.xz').read_bytes()).decode()
    from analog_driver_replay import recorded_trtol
    trtol = recorded_trtol(log)
    if report['assumptions'].get('integrationMethod') not in (None, 'trap'):
        raise ValueError('Only trapezoidal audit is supported')
    abstol = report['assumptions']['solverTolerances']['abstol']
    records = [dict(re.findall(r'(\w+)=([^\s]+)', line)) for line in log.splitlines()
               if line.startswith('TRUNC_AUDIT error ')]
    if not records:
        raise ValueError('No truncation records')
    results = [review_record(r, abstol, trtol) for r in records]
    result = {'qualified':False, 'scope':__doc__,
              'inputAssessmentSha256':sha(args.run/'assessment.json'),
              'engineBaseSourceSha256':build['baseFiles']['src/spicelib/analysis/cktterr.c'],
              'inputLogSha256':hashlib.sha256(log.encode()).hexdigest(),
              'sources':{name:sha(Path(__file__).with_name(name)) for name in
                         ('truncation_arithmetic_review.py', 'analog_driver_replay.py')},
              'controls':{'abstol':abstol,'trtol':trtol,'method':'trap'},
              'maximumDifferenceRelativeRoundingError':max(r['differenceRelativeRoundingError'] for r in results),
              'records':results,
              'boundary':'Exact replay of logged binary64 state histories and tolerance only. Does not recompute Newton solutions, tolerance formation, accepted states or a higher-precision circuit trajectory. Trial flux values are not physical measurements.'}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2)+'\n')
    print(args.out)


if __name__ == '__main__':
    main()
