#!/usr/bin/env python3
"""Screen CPU DC hypotheses with the independent loaded data-valid budget."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

from bus_endpoint_candidates import MODES, resistance
from bus_switching_probe import measurement, ALLOWANCE
from ttl7406_probe import sha

HERE = Path(__file__).resolve().parent
SOURCES = ('u880_output_probe.py', 'u880_output_switching.json', 'bus_limits.json',
           'bus_device_contract.json', 'bus_endpoint_candidates.py',
           'bus_switching_probe.py', 'ttl7406_probe.py')


def cases():
    spec = json.loads((HERE / 'u880_output_switching.json').read_text())
    profile = json.loads((HERE / 'bus_limits.json').read_text())['profiles']['U880']
    conditions = json.loads((HERE / 'bus_device_contract.json').read_text())['devices']['U880']
    vcc = spec['supplyVolts']
    hypotheses = [(mode, resistance(profile, conditions, mode, vcc)) for mode in MODES]
    hypotheses += [('linear-3000', 3000.), ('linear-4000', 4000.)]
    for name, ohms in hypotheses:
        for extra in (0., profile['outputCapacitance']['maximumFarads']):
            for initial in (0., profile['outputLow']['maximumVolts'], spec['ordinaryInputLowVolts']):
                cap = spec['externalCapacitanceFarads'] + extra
                stage = ohms * cap * math.log((vcc - initial) / (vcc - spec['ordinaryInputHighVolts']))
                yield dict(hypothesis=name, highOhms=ohms, supplyVolts=vcc,
                           extraCapacitanceFarads=extra, totalCapacitanceFarads=cap,
                           initialVolts=initial, targetVolts=spec['ordinaryInputHighVolts'],
                           analyticSeconds=stage, maximumSeconds=spec['dataOutputMaximumSeconds'],
                           withinBudget=stage <= spec['dataOutputMaximumSeconds'],
                           internalDelayHeadroomSeconds=spec['dataOutputMaximumSeconds'] - stage,
                           loadedDcHighVolts=vcc - ohms * profile['outputHigh']['sourceMagnitudeAmps'])


def deck(c):
    return '\n'.join(['U880 data-output high-valid necessary screen',
        f'Vdrive drive 0 {c["supplyVolts"]:.17g}',
        f'Rdrive drive out {c["highOhms"]:.17g}',
        f'Cload out 0 {c["totalCapacitanceFarads"]:.17g} IC={c["initialVolts"]:.17g}',
        '.options reltol=1e-8 abstol=1e-12', '.control',
        'tran 0.05n 1u 0 0.05n uic',
        f'meas tran edge_time WHEN v(out)={c["targetVolts"]:.17g} RISE=1',
        'quit', '.endc', '.end', ''])


def verify(out):
    report = json.loads((out / 'assessment.json').read_text())
    if report.get('completed') is not True or report.get('deviceAdmitted') is not False or report.get('qualified') is not False:
        raise ValueError('Changed qualification claim')
    if report['sources'] != {n: sha(HERE / n) for n in SOURCES}:
        raise ValueError('Changed sources')
    expected = list(cases())
    if len(report['cases']) != len(expected):
        raise ValueError('Missing cases')
    for i, (c, actual) in enumerate(zip(expected, report['cases'])):
        folder = out / str(i)
        if actual['case'] != c or (folder / 'probe.cir').read_text() != deck(c):
            raise ValueError('Changed conditions')
        if actual['files'] != {n: sha(folder / n) for n in ('probe.cir', 'ngspice.log')}:
            raise ValueError('Changed evidence')
        value = measurement((folder / 'ngspice.log').read_text())
        if value != actual['measuredSeconds'] or abs(value - c['analyticSeconds']) > ALLOWANCE:
            raise ValueError('Invalid RC result')
        if (value <= c['maximumSeconds']) != c['withinBudget']:
            raise ValueError('Ambiguous boundary')
    print('CPU output screen verified; complete CPU model admission remains open.')


def run(out, executable):
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    engine = Path(shutil.which(executable) or executable).resolve()
    runtime = {'path': str(engine), 'sha256': sha(engine)}
    (out / 'spinit').write_text('* Isolated CPU output RC screen\n')
    report = dict(completed=False, qualified=False, deviceAdmitted=False, runtime=runtime,
        scope='Necessary data-high-valid screen at the published 4.75-V, 100-pF condition. No internal delay or favorable active external driver. Starts at zero, the DC low guarantee, and the ordinary-input low ceiling.',
        capacitanceScope='Zero extra capacitance is the fastest control; 10 pF is the published 25-C capacitance maximum used as a sensitivity hypothesis, not a guaranteed 70-C value.',
        decision='Both endpoint-only CPU hypotheses fail even from 0.8 V without added capacitance. Explicit 3-kohm and 4-kohm alternatives pass these RC/DC screens, but are non-unique hypotheses, not extracted I/V models.',
        notEstablished=['Internal clock-to-drive delay, falling and release behavior', 'Nonlinear I/V and supply law', 'Capacitance at 70 C', 'ROM behavior', 'Operational integration or specimen applicability'],
        sources={n: sha(HERE / n) for n in SOURCES}, cases=[])
    for i, c in enumerate(cases()):
        folder = out / str(i)
        folder.mkdir()
        (folder / 'probe.cir').write_text(deck(c))
        process = subprocess.run([str(engine), '-n', '-b', 'probe.cir'], cwd=folder,
            env=dict(os.environ, SPICE_SCRIPTS=str(out)), capture_output=True, text=True, timeout=30)
        log = process.stdout + process.stderr
        (folder / 'ngspice.log').write_text(log)
        process.check_returncode()
        report['cases'].append(dict(case=c, measuredSeconds=measurement(log),
            files={n: sha(folder / n) for n in ('probe.cir', 'ngspice.log')}))
    if sha(engine) != runtime['sha256']:
        raise ValueError('Changed runtime')
    report['completed'] = True
    (out / 'assessment.json').write_text(json.dumps(report, indent=2) + '\n')
    verify(out)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--ngspice', default='ngspice')
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.verify:
        verify(args.out)
    else:
        run(args.out, args.ngspice)
