#!/usr/bin/env python3
"""Exact residual review of logged Sparse linear systems; no physical qualification."""
import argparse
from fractions import Fraction
import json
import math
from pathlib import Path

from analog_driver_replay import sha


def number(token):
    value = float.fromhex(token)
    if not math.isfinite(value):
        raise ValueError('Nonfinite audit value')
    return Fraction(value)


def parse(log):
    systems, pending, incomplete = [], {}, []
    for line in log.splitlines():
        if not line.startswith('LINEAR_AUDIT '):
            continue
        _, kind, rest = line.split(' ', 2)
        fields = dict(token.split('=', 1) for token in rest.split())
        identity = int(fields.pop('id'))
        if kind == 'begin':
            if identity in pending or any(s['id'] == identity for s in systems):
                raise ValueError('Duplicate linear system identity')
            if int(fields['size']) != int(fields['external']) or number(fields['gmin']) != 0:
                raise ValueError('Only contiguous Sparse systems with zero post-load diagonal gmin are admitted')
            pending[identity] = {'id': identity, 'metadata': fields, 'a': {}, 'b': {}, 'x': {}, 'names': {}}
            continue
        if identity not in pending:
            raise ValueError('Record lacks an open linear system')
        system = pending[identity]
        if kind == 'a':
            key = int(fields['row']), int(fields['col'])
            if key in system['a']:
                raise ValueError('Duplicate matrix coefficient')
            system['a'][key] = number(fields['value'])
        elif kind in ('b', 'x'):
            key = int(fields['row'])
            if key in system[kind]:
                raise ValueError('Duplicate vector entry')
            system[kind][key] = number(fields['value'])
        elif kind == 'name':
            key = int(fields['index'])
            if key in system['names']:
                raise ValueError('Duplicate node name')
            system['names'][key] = fields['name']
        elif kind == 'end':
            size = int(system['metadata']['size'])
            expected = set(range(1, size+1))
            if set(system['b']) != expected or set(system['x']) != expected:
                raise ValueError('Incomplete linear-system vectors')
            if any(row not in expected or col not in expected for row, col in system['a']):
                raise ValueError('Matrix index outside system')
            if not expected <= set(system['names']):
                raise ValueError('Missing equation names')
            systems.append(system)
            del pending[identity]
        else:
            raise ValueError('Unknown audit record: ' + kind)
    incomplete = sorted(pending)
    if not systems:
        raise ValueError('No complete logged linear systems')
    return systems, incomplete


def review(system):
    size = int(system['metadata']['size'])
    residual = {i: -system['b'][i] for i in range(1, size+1)}
    magnitude = {i: abs(system['b'][i]) for i in residual}
    row_norm = {i: Fraction(0) for i in residual}
    for (row, col), value in system['a'].items():
        product = value*system['x'][col]
        residual[row] += product
        magnitude[row] += abs(product)
        row_norm[row] += abs(value)
    ratios = {i: abs(residual[i])/magnitude[i] if magnitude[i] else Fraction(0) for i in residual}
    worst = max(residual, key=lambda i: abs(residual[i]))
    worst_ratio = max(ratios, key=ratios.get)
    norm_bound = max(row_norm.values())*max(map(abs, system['x'].values()))+max(map(abs, system['b'].values()))
    def row_record(i):
        return {'index': i, 'name': system['names'][i], 'residual': float(residual[i]),
                'exactResidual': str(residual[i]), 'sumAbsoluteProductsAndRhs': float(magnitude[i]),
                'componentwiseBackwardError': float(ratios[i])}
    values = [abs(v) for v in system['a'].values() if v]
    return {'id': system['id'], 'timeSeconds': float(number(system['metadata']['time'])),
            'deltaSeconds': float(number(system['metadata']['delta'])),
            'iteration': int(system['metadata']['iteration']), 'order': int(system['metadata']['order']),
            'size': size, 'nonzeroCoefficients': len(values),
            'coefficientMagnitudeRange': [float(min(values)), float(max(values))],
            'maximumAbsoluteSolution': float(max(map(abs, system['x'].values()))),
            'worstAbsoluteResidual': row_record(worst), 'worstComponentwiseResidual': row_record(worst_ratio),
            'normwiseBackwardError': float(abs(residual[worst])/norm_bound) if norm_bound else 0,
            'rowResiduals': [row_record(i) for i in residual if residual[i]]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    parent = json.loads((args.run/'report.json').read_text())
    if parent.get('reproducedEvidence') is not True:
        raise ValueError('Expected a verified logging-only replay')
    if sha(args.run/'ngspice.log') != parent['artifacts']['ngspice.log']:
        raise ValueError('Audit log changed')
    systems, incomplete = parse((args.run/'ngspice.log').read_text())
    result = {'qualified': False, 'scope': __doc__, 'sourceReportSha256': sha(args.run/'report.json'),
              'logSha256': parent['artifacts']['ngspice.log'], 'reviewerSha256': sha(__file__),
              'arithmetic': 'Exact rational products and sums of the logged binary64 coefficients, RHS and solution. Summary floats are presentation only.',
              'systems': [review(s) for s in systems], 'incompleteSystemIds': incomplete,
              'boundary': 'Backward error in selected linear solves only. Mixed voltage/current equation units are not a physical acceptance budget. Does not establish forward error, conditioning, nonlinear convergence, integration correctness or model applicability.'}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2)+'\n')
    print(args.out)


if __name__ == '__main__':
    main()
