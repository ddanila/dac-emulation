"""DC screening of a sourced LS00 topology with explicitly assumed junctions."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from failure_evidence import solver_diagnostic

HERE = Path(__file__).resolve().parent
SOURCE = {'url': 'https://ftpmirror.your.org/pub/misc/bitsavers/components/ti/_dataBooks/1985_TI_The_TTL_Data_Book_Vol_2.pdf',
          'sha256': 'a7d4502eb7c937ace5d3922ed5842674bcd28aec3f3ad98f52a44d1d2d066d7f',
          'topologyPdfPage': 55, 'limitsPdfPage': 59}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    executable = Path(shutil.which(args.ngspice) or args.ngspice).resolve(strict=True)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    model = 'ls00_transistor_candidate.cir'
    shutil.copy2(HERE / model, out / model)
    (out / 'spinit').write_text('* Pure SPICE; no external code models.\n')
    report = {'completed': False, 'qualified': False, 'source': SOURCE,
              'scope': 'DC truth table at TTL input limits, rated output loads, 25 C. No startup, delay, temperature sweep or DL000 equivalence.',
              'assumptions': 'All semiconductor parameters are generic, including junction capacitance and charge storage. Resistors and topology follow the TI drawing. A passing screen does not qualify the model.',
              'engine': {'path': str(executable), 'sha256': sha(executable)},
              'modelSha256': sha(out / model), 'probeSha256': sha(Path(__file__)),
              'spinitSha256': sha(out / 'spinit'),
              'diagnosticHelperSha256': sha(HERE / 'failure_evidence.py'), 'cases': []}
    try:
        for supply in (4.75, 5., 5.25):
            for a, b in ((.8, .8), (.8, 2.), (2., .8), (2., 2.)):
                high = min(a, b) < 1
                label = f'v{supply:g}-a{a:g}-b{b:g}'
                # Positive load current leaves Y; negative injects sink test current.
                load = .0004 if high else -.008
                deck = (f'LS00 transistor DC screen\n.include {model}\n'
                        '.options reltol=1e-8 vntol=1e-10 abstol=1e-14\n.temp 25\n'
                        f'Vcc vp 0 {supply}\nVa a 0 {a}\nVb b 0 {b}\n'
                        f'Xgate a b y vp 0 LS00_TRANSISTOR_CANDIDATE\nIload y 0 {load}\n'
                        '.control\nset wr_singlescale\nset wr_vecnames\nset numdgt=17\nop\n'
                        f'wrdata {label}.txt v(y) i(Vcc) i(Va) i(Vb)\nquit\n.endc\n.end\n')
                path = out / (label + '.cir'); path.write_text(deck)
                record = {'name': label, 'supplyVolts': supply, 'inputVolts': [a,b],
                          'outputHigh': high, 'loadAmps': load,
                          'publishedSupplyCondition': supply == 4.75,
                          'outputLimitVolts': {'minimum': 2.7 if high else 0., 'maximum': supply if high else .5},
                          'deckSha256': sha(path)}
                report['cases'].append(record)
                logpath = out / (label + '.log')
                with logpath.open('w') as log:
                    run = subprocess.run([str(executable), '-n', '-b', path.name], cwd=out,
                                         env=dict(os.environ, SPICE_SCRIPTS=str(out)),
                                         stdout=log, stderr=subprocess.STDOUT, timeout=30)
                record.update(exitCode=run.returncode, logSha256=sha(logpath))
                run.check_returncode()
                diagnostic = solver_diagnostic(logpath.read_text())
                if diagnostic: raise ValueError(diagnostic)
                trace = out / (label + '.txt'); lines = trace.read_text().splitlines()
                if len(lines) != 2 or lines[0].split()[1:] != ['v(y)', 'i(Vcc)', 'i(Va)', 'i(Vb)']:
                    raise ValueError('Unexpected operating point columns')
                values = list(map(float, lines[1].split()))
                if len(values) != 5 or not all(map(math.isfinite, values)):
                    raise ValueError('Invalid operating point')
                _, y, icc, ia, ib = values
                passed = 2.7 <= y <= supply if high else 0 <= y <= .5
                record.update(outputVolts=y, supplyAmps=-icc, inputAmps=[-ia,-ib],
                              outputLimitPassed=passed, traceSha256=sha(trace))
        if sha(executable) != report['engine']['sha256']:
            raise ValueError('Engine changed during execution')
        report['completed'] = True
        report['outputLimitsPassed'] = all(x['outputLimitPassed'] for x in report['cases'])
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'assessment.json').write_text(json.dumps(report, indent=2) + '\n')
    return 0 if report['outputLimitsPassed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
