#!/usr/bin/env python3
"""Constrain CPU pure-delay budgets after finite internal drive ramps."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

from bus_switching_probe import measurement, ALLOWANCE
from ttl7406_probe import sha
from u880_output_probe import SOURCES as OUTPUT_SOURCES, verify as verify_output

HERE = Path(__file__).resolve().parent
SOURCES = ('u880_slew_probe.py', *OUTPUT_SOURCES)


def fraction(t, tau, ramp):
    """Normalized output excursion of a first-order RC driven by a linear ramp."""
    if not ramp:
        return -math.expm1(-t / tau)
    if t <= ramp:
        return (t + tau * math.expm1(-t / tau)) / ramp
    return 1 - tau / ramp * (-math.expm1(-ramp / tau)) * math.exp(-(t - ramp) / tau)


def crossing(tau, ramp, target):
    if not 0 < target < 1 or tau <= 0 or ramp < 0:
        raise ValueError('Invalid monotone RC crossing')
    lo, hi = 0., ramp + 100 * tau
    for _ in range(100):
        mid = (lo + hi) / 2
        if fraction(mid, tau, ramp) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def cases():
    spec = json.loads((HERE / 'u880_output_switching.json').read_text())
    profile = json.loads((HERE / 'bus_limits.json').read_text())['profiles']['U880']
    supply = spec['supplyVolts']
    low_r = profile['outputLow']['maximumVolts'] / profile['outputLow']['sinkAmps']
    for high_r in (3000., 4000.):
        for extra in (0., profile['outputCapacitance']['maximumFarads']):
            for ramp in (0., 10e-9, 30e-9, 60e-9):
                for edge in ('rise', 'fall'):
                    cap = spec['externalCapacitanceFarads'] + extra
                    resistance = high_r if edge == 'rise' else low_r
                    initial, final = (0., supply) if edge == 'rise' else (supply, 0.)
                    target = spec['ordinaryInputHighVolts'] if edge == 'rise' else spec['ordinaryInputLowVolts']
                    stage = crossing(resistance * cap, ramp, (target - initial) / (final - initial))
                    yield dict(highOhms=high_r, extraCapacitanceFarads=extra,
                        rampSeconds=ramp, edge=edge, resistanceOhms=resistance,
                        totalCapacitanceFarads=cap, initialVolts=initial, finalVolts=final,
                        targetVolts=target, analyticSeconds=stage,
                        maximumSeconds=spec['dataOutputMaximumSeconds'],
                        internalDelayHeadroomSeconds=spec['dataOutputMaximumSeconds']-stage,
                        withinBudget=stage <= spec['dataOutputMaximumSeconds'])


def deck(c):
    drive = (f'PWL(0 {c["initialVolts"]:.17g} {c["rampSeconds"]:.17g} {c["finalVolts"]:.17g})'
             if c['rampSeconds'] else f'{c["finalVolts"]:.17g}')
    return '\n'.join(['CPU finite internal drive-slew hypothesis', 'Vdrive drive 0 ' + drive,
        f'Rdrive drive out {c["resistanceOhms"]:.17g}',
        f'Cload out 0 {c["totalCapacitanceFarads"]:.17g} IC={c["initialVolts"]:.17g}',
        '.options reltol=1e-8 abstol=1e-12', '.control', 'tran 0.02n 1u 0 0.02n uic',
        f'meas tran edge_time WHEN v(out)={c["targetVolts"]:.17g} {c["edge"].upper()}=1',
        'quit', '.endc', '.end', ''])


def budgets(rows):
    groups = {}
    for i, c in enumerate(rows):
        key = (c['highOhms'], c['extraCapacitanceFarads'], c['rampSeconds'])
        if key not in groups or c['internalDelayHeadroomSeconds'] < groups[key]['rawHeadroomSeconds']:
            bound = c['internalDelayHeadroomSeconds']
            groups[key] = dict(highOhms=key[0], extraCapacitanceFarads=key[1], rampSeconds=key[2],
                limitingCaseIndex=i, rawHeadroomSeconds=bound,
                internalDelayIntervalSeconds=[0., bound] if bound >= 0 else None)
    return list(groups.values())


def verify(out):
    verify_output(HERE / 'reports/u880-output-candidates')
    report = json.loads((out / 'assessment.json').read_text())
    expected = list(cases())
    if report.get('completed') is not True or report.get('qualified') is not False or report.get('deviceAdmitted') is not False:
        raise ValueError('Invalid admission status')
    if report['sources'] != {n: sha(HERE / n) for n in SOURCES}:
        raise ValueError('Changed sources')
    if report['baselineReceiptSha256'] != sha(HERE / 'reports/u880-output-candidates/assessment.json'):
        raise ValueError('Changed baseline')
    if len(report['cases']) != len(expected) or report['jointDelayBudgets'] != budgets(expected):
        raise ValueError('Changed scope or delay budget')
    for i, (c, actual) in enumerate(zip(expected, report['cases'])):
        folder = out / str(i)
        if actual['case'] != c or (folder / 'probe.cir').read_text() != deck(c):
            raise ValueError('Changed conditions')
        if actual['files'] != {n: sha(folder / n) for n in ('probe.cir', 'ngspice.log')}:
            raise ValueError('Changed retained evidence')
        value = measurement((folder / 'ngspice.log').read_text())
        if value != actual['measuredSeconds'] or abs(value - c['analyticSeconds']) > ALLOWANCE:
            raise ValueError('Analytic/SPICE ramp disagreement')
        if (value <= c['maximumSeconds']) != c['withinBudget']:
            raise ValueError('Ambiguous classification')
    print('Finite-slew CPU constraints verified; device admission remains open.')


def run(out, executable):
    verify_output(HERE / 'reports/u880-output-candidates')
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    engine = Path(shutil.which(executable) or executable).resolve()
    runtime = dict(path=str(engine), sha256=sha(engine))
    (out / 'spinit').write_text('* CPU drive-slew screening\n')
    rows = list(cases())
    report = dict(completed=False, qualified=False, deviceAdmitted=False, runtime=runtime,
        scope='Linear Thevenin drive ramps with fixed final-state resistance. High drive ramps 0 to 4.75 V; low drive ramps 4.75 to 0 V. No simultaneous driver overlap, internal state or nonlinear transistor inference.',
        interpretation='Joint nonnegative pure transport-delay intervals after accounting for both output polarities and finite drive ramp. Null intervals reject that combination even at zero internal delay. Ramp durations are explicit alternatives, not published slew values.',
        conditions='Published 4.75-V/100-pF data-valid screen. Added 10 pF remains a sensitivity assumption from the 25-C capacitance specification, not a 70-C guarantee. Output-valid endpoints are 2 V high and 0.8 V low.',
        notEstablished=['Actual drive shape, nonlinear I/V, temperature and supply law', 'Release and enable dynamics', 'Internal delay calibration', 'ROM, operational board and specimen qualification'],
        sources={n: sha(HERE / n) for n in SOURCES},
        baselineReceiptSha256=sha(HERE / 'reports/u880-output-candidates/assessment.json'),
        jointDelayBudgets=budgets(rows), cases=[])
    for i, c in enumerate(rows):
        folder = out / str(i)
        folder.mkdir()
        (folder / 'probe.cir').write_text(deck(c))
        result = subprocess.run([str(engine), '-n', '-b', 'probe.cir'], cwd=folder,
            env=dict(os.environ, SPICE_SCRIPTS=str(out)), capture_output=True, text=True, timeout=30)
        log = result.stdout + result.stderr
        (folder / 'ngspice.log').write_text(log)
        result.check_returncode()
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
