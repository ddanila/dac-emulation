#!/usr/bin/env python3
"""Inspect internal gate states without changing a retained oscillator AC circuit."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from failure_evidence import capture, solver_diagnostic
from ls00_branch_probe import topology, signals_for, balances
from ls00_transistor_probe import sha
from oscillator_ac_probe import NODES
from oscillator_disturbance import BUDGET

HERE = Path(__file__).resolve().parent
GATES = [('first', 'xa7_3', 'n_osc_rc', 'n_osc1'),
         ('second', 'xa7_1', 'n_osc1', 'n_osc2'),
         ('buffer', 'xa7_2', 'n_osc2', 'n_osc_out')]
PARAMETERS = ['vbe', 'vbc', 'gm', 'gpi', 'go']


def expand(signal, gate, input_node, output_node):
    return (signal.replace('xgate', gate + '.xgate')
            .replace('v(a)', f'v({input_node})').replace('v(y)', f'v({output_node})')
            .replace('v(vp)', 'v(n_p5v)'))


def read_op(text, signals):
    lines = text.splitlines()
    if len(lines) != 2 or lines[0].lower().split()[1:] != [s.lower() for s in signals]:
        raise ValueError('Unexpected operating-point columns')
    row = list(map(float, lines[1].split()))
    if len(row) != len(signals) + 1 or not all(map(math.isfinite, row)):
        raise ValueError('Invalid operating-point values')
    return dict(zip(signals, row[1:]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ac', type=Path, required=True, help='Completed matched-plateau AC capture')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--ngspice', default='ngspice')
    args = parser.parse_args()
    source = args.ac.resolve()
    prior = json.loads((source / 'assessment.json').read_text())
    engine = Path(shutil.which(args.ngspice) or args.ngspice).resolve(strict=True)
    if prior.get('completed') is not True or prior['engineSha256'] != sha(engine):
        raise ValueError('Incomplete capture or different runtime')
    expected = dict(prior['artifacts'], **{'model.cir': prior['modelSha256'],
                                         'spinit': prior['spinitSha256']})
    for name, digest in expected.items():
        if sha(source / name) != digest:
            raise ValueError('Stale source artifact: ' + name)
    elements = topology((source / 'model.cir').read_text())
    basic = signals_for(elements)
    extra = ['@' + name + '[' + parameter + ']' for kind, name, _, _ in elements
             if kind == 'q' for parameter in PARAMETERS]
    signals = list(dict.fromkeys(list(NODES) + [expand(s, *gate[1:])
                                for gate in GATES for s in basic + extra]))
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    for name in ['model.cir', 'spinit']:
        shutil.copyfile(source / name, out / name)
    report = {'completed': False, 'qualified': False,
              'scope': 'Internal states of the unchanged candidate circuit at a matched external-node plateau. No independent transistor-equation check, physical device calibration, transient internal-state identity or stability claim.',
              'sourceAssessmentSha256': sha(source / 'assessment.json'),
              'sourceArtifacts': expected, 'engineSha256': sha(engine),
              'modelSha256': prior['modelSha256'], 'connectivitySha256': prior['connectivitySha256'],
              'sources': {p.name: sha(p) for p in [Path(__file__), HERE / 'ls00_branch_probe.py',
                  HERE / 'ls00_transistor_probe.py', HERE / 'failure_evidence.py',
                  HERE / 'oscillator_ac_probe.py', HERE / 'oscillator_disturbance.py']}}
    try:
        circuit = (source / 'probe.cir').read_text().split('.control')[0]
        (out / 'probe.cir').write_text(circuit + '.control\nset numdgt=17\nset wr_singlescale\nset wr_vecnames\nop\nwrdata internal.txt ' + ' '.join(signals) + '\nquit\n.endc\n.end\n')
        with (out / 'ngspice.log').open('w') as log:
            subprocess.run([str(engine), '-n', '-b', 'probe.cir'], cwd=out,
                env=dict(os.environ, SPICE_SCRIPTS=str(out)), stdout=log,
                stderr=subprocess.STDOUT, check=True, timeout=60)
        if solver_diagnostic((out / 'ngspice.log').read_text()):
            raise ValueError('Solver diagnostic')
        values = read_op((out / 'internal.txt').read_text(), signals)
        difference = max(abs(values[s] - prior['operatingPointVolts'][s]) for s in NODES)
        report['externalNodeDifferenceVolts'] = difference
        if difference > BUDGET:
            raise ValueError('Operating point changed')
        report['gates'] = {}
        for label, *gate in GATES:
            local = {s: values[expand(s, *gate)] for s in basic + extra}
            # External output loading is absent from this per-gate element list.
            kcl = {n: v for n, v in balances(elements, local).items() if n != 'y'}
            report['gates'][label] = {'values': local, 'internalNodeKcl': kcl}
            if not all(v['balanced'] for v in kcl.values()):
                raise ValueError('Internal current balance failed: ' + label)
        if sha(engine) != report['engineSha256']:
            raise ValueError('Runtime changed')
        report['artifacts'] = {name: sha(out / name) for name in
                               ['probe.cir', 'internal.txt', 'ngspice.log', 'model.cir', 'spinit']}
        report['completed'] = True
    except Exception as error:
        report['error'] = str(error)
        report['failureEvidence'] = capture(out, ['probe.cir', 'internal.txt', 'ngspice.log'])
        raise
    finally:
        (out / 'assessment.json').write_text(json.dumps(report, indent=2) + '\n')
    print(out / 'assessment.json')


if __name__ == '__main__':
    main()
