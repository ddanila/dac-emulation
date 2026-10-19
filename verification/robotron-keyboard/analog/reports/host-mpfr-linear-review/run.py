#!/usr/bin/env python3
"""Check MPFR kernel against independent Decimal solves of recorded equations."""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

ANALOG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ANALOG))
from analog_driver_replay import sha
from linear_system_review import parse, review
from linear_precision_review import solve


def execute(binary, bits, stimulus):
    start = time.monotonic()
    result = subprocess.run([str(binary), str(bits)], input=stimulus,
                            capture_output=True, text=True, timeout=60)
    return result, time.monotonic()-start


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--system-id', type=int, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    parent = json.loads((args.run/'report.json').read_text())
    log = args.run/'ngspice.log'
    if not parent.get('reproducedEvidence') or sha(log) != parent['artifacts']['ngspice.log']:
        raise ValueError('Expected verified unchanged audit')
    systems, _ = parse(log.read_text())
    system = next(s for s in systems if s['id'] == args.system_id)
    n = int(system['metadata']['size'])
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).with_name('solve.c')
    flags = shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','mpfr','gmp'],text=True))
    command = ['clang','-O2','-Wall','-Wextra','-Werror',str(source),*flags,'-o',str(out/'solve')]
    subprocess.run(command,check=True,capture_output=True,text=True)
    libraries = {}
    for package in ('mpfr','gmp'):
        directory = Path(subprocess.check_output(['pkg-config','--variable=libdir',package],text=True).strip())
        paths = list(directory.glob('lib'+package+'.dylib')) or list(directory.glob('lib'+package+'.so'))
        if len(paths) != 1:
            raise ValueError('Cannot identify dynamic library '+package)
        libraries[str(paths[0].resolve())] = sha(paths[0])
    native = {}
    # First row forces a pivot swap; exact solution is x=1, y=2.
    for name, stimulus, expected in (
        ('pivot', '2 3\n1 2 1\n2 1 1\n2 2 1\n2\n3\n', {1:Fraction(1),2:Fraction(2)}),
        ('singular','2 4\n1 1 1\n1 2 1\n2 1 2\n2 2 2\n2\n4\n',None),
        ('nonfinite','1 1\n1 1 nan\n1\n',None)):
        result, elapsed = execute(out/'solve',256,stimulus)
        actual = {int(i):Fraction(float.fromhex(v)) for i,v in
                  (line.split() for line in result.stdout.splitlines())}
        passed = result.returncode != 0 if expected is None else result.returncode == 0 and actual == expected
        native[name] = {'passed':passed,'exitCode':result.returncode}
        if not passed: raise ValueError('Native control failed: '+name)
    stimulus = f'{n} {len(system["a"])}\n'
    stimulus += ''.join(f'{i} {j} {float(v).hex()}\n' for (i,j),v in sorted(system['a'].items()))
    stimulus += ''.join(float(system['b'][i]).hex()+'\n' for i in range(1,n+1))
    (out/'input.txt').write_text(stimulus)
    reference = solve(system,160)
    cases = {}; previous = None
    for bits in (256,512):
        result, elapsed = execute(out/'solve',bits,stimulus)
        result.check_returncode()
        (out/f'output-{bits}.txt').write_text(result.stdout)
        lines = [line.split() for line in result.stdout.splitlines()]
        solution = {int(i):Fraction(float.fromhex(v)) for i,v in lines}
        if len(lines) != n or set(solution) != set(range(1,n+1)):
            raise ValueError('Incomplete or duplicate output')
        error = max(abs(solution[i]-reference[i])/max(Fraction(1),abs(reference[i])) for i in solution)
        passed = error <= Fraction(1,2**52)
        cases[str(bits)] = {'passed':passed,'elapsedSeconds':elapsed,
            'maximumScaledDifferenceFromDecimal160':float(error),
            'maximumAbsoluteDifferenceFromPreviousPrecision':None if previous is None else
                float(max(abs(solution[i]-previous[i]) for i in solution)),
            'binary64OutputResidualReview':review(dict(system,x=solution))}
        if not passed: raise ValueError('Independent reference disagreement')
        previous = solution
    if any(sha(p) != digest for p,digest in libraries.items()):
        raise ValueError('Library changed during review')
    report = {'qualified':False,'completed':True,'scope':__doc__,
        'sourceReportSha256':sha(args.run/'report.json'),'logSha256':sha(log),'systemId':args.system_id,
        'sources':{str(p.relative_to(ANALOG)):sha(p) for p in
            [Path(__file__),source,ANALOG/'engine-patches/mpfr_linear_solver.h',
             ANALOG/'linear_precision_review.py',ANALOG/'linear_system_review.py']},
        'build':{'command':command,'compiler':subprocess.check_output(['clang','--version'],text=True),
            'versions':subprocess.check_output(['pkg-config','--modversion','mpfr','gmp'],text=True),
            'libraries':libraries,'executableSha256':sha(out/'solve')},
        'nativeControls':native,'cases':cases,
        'comparisonCriterion':'abs(MPFR binary64 output - Decimal160) / max(1, abs(Decimal160)) <= 2^-52 per coordinate; a numerical kernel check, not a physical tolerance.',
        'boundary':'Frozen binary64 equations only. Returned values are binary64; residuals include output rounding. Does not repair stamping, nonlinear iteration, integration history or establish circuit qualification.'}
    report['artifacts']={p.name:sha(p) for p in out.iterdir() if p.is_file()}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(out/'report.json')


if __name__ == '__main__':
    main()
