#!/usr/bin/env python3
"""Compare fresh Sparse factorizations with and without exact power-of-two scaling."""
import argparse
from fractions import Fraction
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

ANALOG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ANALOG))
from analog_driver_replay import sha
from linear_system_review import parse, review


def reciprocal_power(value):
    exponent = math.frexp(float(value))[1] if value else 0
    return Fraction(1, 2**exponent) if exponent >= 0 else Fraction(2**-exponent)


def exact_float(value):
    converted = float(value)
    if not math.isfinite(converted) or Fraction(converted) != value:
        raise ValueError('Scaling would round, underflow or overflow')
    return converted


def scales(system):
    n = int(system['metadata']['size'])
    rows = {i: reciprocal_power(max((abs(v) for (r,c),v in system['a'].items() if r == i), default=0))
            for i in range(1, n+1)}
    cols = {i: reciprocal_power(max((abs(v*rows[r]) for (r,c),v in system['a'].items() if c == i), default=0))
            for i in range(1, n+1)}
    return rows, cols


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--system-id', type=int, required=True)
    parser.add_argument('--ngspice-build', type=Path, required=True)
    parser.add_argument('--ngspice-source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    parent = json.loads((args.run/'report.json').read_text())
    if not parent.get('reproducedEvidence') or sha(args.run/'ngspice.log') != parent['artifacts']['ngspice.log']:
        raise ValueError('Expected a verified unchanged audit')
    systems, _ = parse((args.run/'ngspice.log').read_text())
    system = next(s for s in systems if s['id'] == args.system_id)
    n = int(system['metadata']['size'])
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    compiler = shutil.which('clang')
    if not compiler:
        raise ValueError('clang is required for this reproducible diagnostic')
    source = Path(__file__).with_name('solve.c')
    libraries = [args.ngspice_build/'src/maths/sparse/.libs/libsparse.a',
                 args.ngspice_build/'src/misc/.libs/libmisc.a']
    command = [compiler, '-O2', '-I'+str(args.ngspice_source/'src/include'),
               '-I'+str(args.ngspice_build/'src/include'), str(source),
               *map(str,libraries), '-lm', '-o', str(out/'solve')]
    subprocess.run(command, check=True, capture_output=True, text=True)
    report = {'qualified': False, 'scope': __doc__, 'sourceReportSha256': sha(args.run/'report.json'),
              'systemId': args.system_id, 'sources': {'run.py': sha(__file__), 'solve.c': sha(source),
                                                     'linear_system_review.py': sha(ANALOG/'linear_system_review.py')},
              'build': {'command': command, 'compiler': subprocess.check_output([compiler, '--version'], text=True),
                        'libraries': {str(p): sha(p) for p in libraries}, 'executableSha256': sha(out/'solve')},
              'pivotThresholds': {'relative': .001, 'absolute': 1e-13}, 'cases': {},
              'boundary': 'Same frozen stamped system and Sparse library; fresh ordering in both cases. Does not reproduce the transient solver pivot history or rerun nonlinear/integration steps. Unscaled row residuals are diagnostic, not physical qualification.'}
    for scaled in (False, True):
        label = 'scaled' if scaled else 'fresh'
        rows, cols = scales(system) if scaled else ({i: Fraction(1) for i in range(1,n+1)},)*2
        text = f'{n} {len(system["a"])}\n'
        text += ''.join(f'{i} {j} {exact_float(v*rows[i]*cols[j]).hex()}\n'
                        for (i,j),v in sorted(system['a'].items()))
        text += ''.join(exact_float(system['b'][i]*rows[i]).hex()+'\n' for i in range(1,n+1))
        (out/(label+'-input.txt')).write_text(text)
        process = subprocess.run([str(out/'solve')], input=text, capture_output=True, text=True, timeout=60)
        (out/(label+'-output.txt')).write_text(process.stdout)
        (out/(label+'-stderr.txt')).write_text(process.stderr)
        result = {'exitCode': process.returncode}
        if process.returncode == 0:
            solution = {}
            for line in process.stdout.splitlines():
                key, value = line.split()
                index = int(key)
                if index in solution:
                    raise ValueError('Duplicate solution index')
                solution[index] = Fraction(exact_float(Fraction(float.fromhex(value))*cols[index]))
            if set(solution) != set(range(1,n+1)):
                raise ValueError('Incomplete solution')
            result['unscaledResidualReview'] = review(dict(system, x=solution))
            result['rowScale'] = {str(i): exact_float(v).hex() for i,v in rows.items()}
            result['columnScale'] = {str(i): exact_float(v).hex() for i,v in cols.items()}
        report['cases'][label] = result
    if any(sha(p) != report['build']['libraries'][str(p)] for p in libraries):
        raise ValueError('Library changed during review')
    report['artifacts'] = {p.name: sha(p) for p in out.iterdir() if p.is_file()}
    (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(out/'report.json')


if __name__ == '__main__':
    main()
