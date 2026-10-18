#!/usr/bin/env python3
"""Replay retained gate-transfer fixtures in Xyce with explicit temperature mapping."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
from failure_evidence import capture
from ls00_transistor_probe import sha
from ls00_transfer_fixture import read_sweep, compare

HERE = Path(__file__).resolve().parent
OPTIONS = '.options reltol=1e-8 vntol=1e-10 abstol=1e-14 gmin=1e-15'


def deck(text):
    if text.count('.control') != 1:
        raise ValueError('Unsupported control block')
    circuit, control = text.split('.control')
    if circuit.count('.temp 25\n') != 1 or circuit.count(OPTIONS + '\n') != 1:
        raise ValueError('Unsupported temperature or solver settings')
    circuit = circuit.replace('.temp 25\n', '.options device temp=25 tnom=27 gmin=1e-15\n')
    circuit = circuit.replace(OPTIONS, '.options nonlin reltol=1e-8 abstol=1e-14')
    sweeps = re.findall(r'^dc Vin [^\n]+$', control, re.M)
    if len(sweeps) != 1:
        raise ValueError('Unsupported sweep')
    return circuit + '.' + sweeps[0] + '\n.print dc format=noindex precision=17 file=transfer.txt V(a) V(y) I(Vin)\n.end\n'


def rows(text, step, reverse):
    lines = text.splitlines()
    if not lines or lines[0].split() != ['V(A)', 'V(Y)', 'I(VIN)'] or lines[-1] != 'End of Xyce(TM) Simulation':
        raise ValueError('Incomplete Xyce transfer output')
    return read_sweep('scale v(y) i(Vin)\n' + '\n'.join(lines[1:-1]), step, reverse)


def check_log(text):
    if re.search(r'\b(?:warning|error|fatal)\b', text, re.I):
        raise ValueError('Xyce diagnostic')
    for label in ['Number Failed Steps Attempted', 'Number Failed Linear Solves', 'Number Nonlinear Convergence Failures']:
        match = re.search(re.escape(label) + r':\s*(\d+)', text)
        if not match or int(match[1]) != 0:
            raise ValueError('Missing or failed solver summary: ' + label)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True, help='Completed ls00_transfer_fixture capture')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--xyce', required=True)
    args = p.parse_args(); source = args.source.resolve()
    prior = json.loads((source / 'assessment.json').read_text())
    if prior.get('completed') is not True or sha(source / 'model.cir') != prior['modelSha256']:
        raise ValueError('Incomplete source or stale model')
    for case in prior['cases']:
        for filename, digest in case['artifacts'].items():
            if sha(source / filename) != digest:
                raise ValueError('Stale source artifact')
    executable = Path(shutil.which(args.xyce) or args.xyce).resolve(strict=True)
    runtime_files = [executable]
    library = executable.parent.parent / 'lib/libxyce.dylib'
    if library.exists(): runtime_files.append(library)
    runtime = {str(f): sha(f) for f in runtime_files}
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(source / 'model.cir', out / 'model.cir')
    report = {'completed': False, 'qualified': False, 'runtime': runtime,
        'version': subprocess.check_output([str(executable), '-v'], text=True).strip(),
        'modelSha256': prior['modelSha256'], 'sourceAssessmentSha256': sha(source / 'assessment.json'),
        'sources': {f.name: sha(f) for f in [Path(__file__), HERE / 'ls00_transfer_fixture.py', HERE / 'ls00_transistor_probe.py', HERE / 'failure_evidence.py']},
        'scope': 'Same model bytes and isolated fixtures, independent solver. Temperature is explicitly 25 C with nominal 27 C. Nonlinear tolerances have different solver semantics; branch agreement is not calibration or a stability proof.',
        'cases': [], 'directionComparisons': []}
    traces = {}
    try:
        for case in prior['cases']:
            name = case['name']; folder = out / name; folder.mkdir()
            # Keep the copied model immutable and shared across the fixture replays.
            converted = deck((source / (name + '.cir')).read_text()).replace('.include model.cir', '.include ../model.cir')
            (folder / 'probe.cir').write_text(converted)
            with (folder / 'xyce.log').open('w') as log:
                subprocess.run([str(executable), 'probe.cir'], cwd=folder, stdout=log,
                               stderr=subprocess.STDOUT, check=True, timeout=60)
            check_log((folder / 'xyce.log').read_text())
            xy = rows((folder / 'transfer.txt').read_text(), case['stepVolts'], case['reverse'])
            ng = read_sweep((source / (name + '.txt')).read_text(), case['stepVolts'], case['reverse'])
            difference = compare(ng, xy)
            report['cases'].append({'name': name,
                'maximumSolverOutputDifferenceVolts': difference['maximumOutputDifferenceVolts'],
                'inputVoltsAtMaximumDifference': difference['inputVolts'],
                'ngspiceOutputVolts': difference['forwardOutputVolts'], 'xyceOutputVolts': difference['reverseOutputVolts'],
                'artifacts': {f.name: sha(f) for f in folder.iterdir() if f.is_file()}})
            key = (case['loadConnection'], case['complementaryInput'], case['stepVolts'])
            traces.setdefault(key, {})[case['reverse']] = xy
        for (load, input_, step), directions in traces.items():
            report['directionComparisons'].append({'loadConnection': load, 'complementaryInput': input_,
                'stepVolts': step, **compare(directions[False], directions[True])})
        if any(sha(Path(f)) != digest for f, digest in runtime.items()):
            raise ValueError('Runtime changed')
        report['completed'] = True
    except Exception as error:
        report['error'] = str(error)
        report['failureEvidence'] = capture(out, [str(f.relative_to(out)) for f in out.rglob('*') if f.is_file()])
        raise
    finally:
        (out / 'assessment.json').write_text(json.dumps(report, indent=2) + '\n')
    print(out / 'assessment.json')


if __name__ == '__main__': main()
