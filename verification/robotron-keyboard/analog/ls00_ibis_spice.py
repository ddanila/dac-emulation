"""Cross-check local typical IBIS DC curves in SPICE against analytic load lines.

Generated decks contain vendor table data and remain local. This does not import
the faulty package map or install a TI model as a DL000 board default.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from circuit import load
from clock_output_probe import wiring
from failure_evidence import solver_diagnostic
from ls00_ibis_loadline import SOURCE_SHA, equilibrium, tables

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def expression(points, variable):
    """Continuous linear segments represented by slope changes, without smoothing."""
    slopes = [(b[1] - a[1]) / (b[0] - a[0]) for a, b in zip(points, points[1:])]
    terms = [f'({points[0][1]:.17g})', f'({slopes[0]:.17g})*({variable}-({points[0][0]:.17g}))']
    for i in range(1, len(slopes)):
        terms.append(f'({slopes[i] - slopes[i - 1]:.17g})*max(0,{variable}-({points[i][0]:.17g}))')
    return '+\n+ '.join(terms)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ibis', type=Path, required=True)
    parser.add_argument('--ngspice', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if sha(args.ibis) != SOURCE_SHA:
        raise ValueError('Unreviewed IBIS input')
    curves = tables(args.ibis.read_text(encoding='latin-1'))
    components, connectivity_sha = load()
    wiring(components, 0)
    resistance = float(components['R10.3']['type'])
    executable = shutil.which(args.ngspice)
    if not executable:
        raise ValueError('ngspice not found')
    executable = Path(executable).resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / 'spinit').write_text('* Pure SPICE DC comparison; no external code models.\n')
    shutil.copyfile(HERE / 'ls_nand_pullup.cir', out / 'ls_nand_pullup.cir')
    report = {'qualified': False, 'completed': False, 'cases': [],
              'ibisSha256': SOURCE_SHA, 'connectivitySha256': connectivity_sha,
              'engine': {'path': str(executable), 'sha256': sha(executable)},
              'spinitSha256': sha(out / 'spinit'), 'gateModelSha256': sha(out / 'ls_nand_pullup.cir'),
              'scope': '5 V typical static output comparison, ideal closed bridge, no CPU leakage or package parasitics. Both output states are solved separately, not interpolated as switching behavior.',
              'boundary': 'SPICE agreement validates curve conversion only. TI output curves do not calibrate DL000, undervoltage startup or timing. Generated vendor-derived decks remain local.',
              'sources': {name: sha(HERE / name) for name in
                          ('ls00_ibis_spice.py', 'ls00_ibis_loadline.py', 'circuit.py', 'clock_output_probe.py', 'failure_evidence.py')}}
    try:
        for state, table in [('high', 'pullup'), ('low', 'pulldown')]:
            points = sorted((5 - r[0] if state == 'high' else r[0], r[1]) for r in curves[table])
            expected = equilibrium(points, 5, resistance)
            guess = 3.5 if state == 'high' else .4
            # Feed the same supply/pullup to independent output nodes. The
            # behavioural driver uses its existing control polarity and model.
            deck = ('Typical output DC comparison\n.include ls_nand_pullup.cir\n'
                    '.options reltol=1e-10 vntol=1e-12 abstol=1e-15\n.temp 25\n'
                    f'.nodeset v(reference)={guess} v(candidate)={guess}\n'
                    'Vcc vcc 0 5\n' + f'Vin control 0 {0 if state == "high" else 5}\n'
                    f'Rreference vcc reference {resistance:.17g}\n'
                    f'Rcandidate vcc candidate {resistance:.17g}\n'
                    'Xcandidate control control candidate vcc 0 LS_NAND_NOMINAL\n'
                    'Breference reference 0 I=' + expression(points, 'V(reference)') + '\n'
                    '.control\nset wr_singlescale\nset wr_vecnames\nset numdgt=17\nop\n'
                    f'wrdata {state}.txt v(reference) v(candidate)\nquit\n.endc\n.end\n')
            path = out / (state + '.cir')
            path.write_text(deck)
            record = {'state': state, 'deckSha256': sha(path), 'analytical': expected,
                      'newtonInitialGuessVolts': guess,
                      'initialGuessBoundary': 'Nodeset guides the DC solve; it is not a clamp or an initial condition for a transient.'}
            report['cases'].append(record)
            with (out / (state + '.log')).open('w') as log:
                result = subprocess.run([str(executable), '-n', '-b', path.name], cwd=out,
                                        env=dict(os.environ, SPICE_SCRIPTS=str(out)), stdout=log,
                                        stderr=subprocess.STDOUT, timeout=30)
            record.update(exitCode=result.returncode, logSha256=sha(out / (state + '.log')))
            result.check_returncode()
            diagnostic = solver_diagnostic((out / (state + '.log')).read_text())
            if diagnostic:
                raise ValueError(diagnostic)
            lines = (out / (state + '.txt')).read_text().splitlines()
            if len(lines) != 2 or lines[0].split()[1:] != ['v(reference)', 'v(candidate)']:
                raise ValueError('Unexpected DC output')
            _, reference, candidate = map(float, lines[1].split())
            if not 0 <= reference <= 5 or not 0 <= candidate <= 5:
                raise ValueError('Out-of-range DC solution')
            error = abs(reference - expected['outputVolts'])
            record.update(referenceVolts=reference, candidateVolts=candidate,
                          candidateMinusReferenceVolts=candidate-reference,
                          analyticalErrorVolts=error, analyticalBudgetVolts=1e-9,
                          traceSha256=sha(out / (state + '.txt')))
            if error > 1e-9:
                raise ValueError('SPICE and analytic current balance disagree')
        if sha(executable) != report['engine']['sha256']:
            raise ValueError('Engine changed during execution')
        report['completed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'assessment.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
