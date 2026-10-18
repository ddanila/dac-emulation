#!/usr/bin/env python3
"""Exercise finite CPU WR drive against the transistor clock gate and cable."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

from circuit import load, node
from failure_evidence import solver_diagnostic
from ttl7406_output_probe import driver_circuit, checked_dc_reference, sha
from write_control import wiring

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    executable = Path(shutil.which(args.ngspice)).resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / 'spinit').write_text('* Pure SPICE fixture, no external code models.\n')
    env = dict(os.environ, SPICE_SCRIPTS=str(out))
    report = {'passed': False, 'qualified': False, 'scope': __doc__, 'runs': [],
              'executableSha256': sha(executable), 'spinitSha256': sha(out / 'spinit'),
              'dcCandidateReportSha256': checked_dc_reference(),
              'sources': {name: sha(HERE / name) for name in (
                  'write_control_probe.py', 'write_control.py', 'ttl7406_output_probe.py',
                  'ttl7406_nominal.cir', 'output_circuit.py', 'circuit.py',
                  'bus_limits.json', 'failure_evidence.py')},
              'limitations': 'Synthetic ownership stimulus, not firmware or U880 phase qualification. '
                             'Transistor storage and junction capacitances are uncalibrated.'}
    try:
        components, report['connectivitySha256'] = load()
        loads, report['wrCircuit'] = wiring(components, json.loads((HERE / 'bus_limits.json').read_text()), 3)
        outputs, report['outputCircuit'] = driver_circuit(components, '7406-dc', 1000, electrical_clock_input=True)
        meta = report['outputCircuit']
        ground = meta['hostGround']
        signals = f'v({node(report["wrCircuit"]["net"])}) v({meta["serial"]["clock"]["cable"]},{ground}) @bwr_low[i] @bwr_high[i] i(Vdriver_supply)'
        for step in (5, 2.5):
            run = out / f'step-{step}ns'
            run.mkdir()
            # High, low, released, low again. Release voltage is determined by
            # the modeled input bias; it is deliberately not assigned a logic value.
            deck = '\n'.join(['CPU WR electrical loading fixture',
                f'Vhost {meta["hostSupply"]} {ground} 5', *outputs, *loads,
                'Vdata data_intent 0 0', 'Vsiso siso_intent 0 0', 'Vcaps caps_intent 0 0',
                'Vwr_high wr_high 0 PWL(0 5 10u 5 10.001u 0 40u 0)',
                'Vwr_low wr_low 0 PWL(0 0 10u 0 10.001u 5 20u 5 20.001u 0 30u 0 30.001u 5 40u 5)',
                '.save ' + signals, '.control', 'set wr_singlescale', 'set wr_vecnames', 'set numdgt=17',
                f'tran {step}n 40u', 'wrdata trace.txt ' + signals, 'quit', '.endc', '.end', ''])
            (run / 'probe.cir').write_text(deck)
            proc = subprocess.run([str(executable), '-n', '-b', 'probe.cir'], cwd=run, env=env,
                                  capture_output=True, text=True, timeout=60)
            log = proc.stdout + proc.stderr
            (run / 'ngspice.log').write_text(log)
            proc.check_returncode()
            if solver_diagnostic(log):
                raise ValueError('Solver diagnostic: ' + str(solver_diagnostic(log)))
            rows = [list(map(float, line.split())) for line in (run / 'trace.txt').read_text().splitlines()[1:]]
            if (not rows or any(len(r) != 6 or not all(map(math.isfinite, r)) for r in rows)
                    or rows[0][0] > 1e-9 or abs(rows[-1][0] - 40e-6) > 1e-12
                    or any(b[0] < a[0] or b[0] - a[0] > step * 1e-9 + 1e-15 for a, b in zip(rows, rows[1:]))):
                raise ValueError('Incomplete WR waveform')
            samples = [min(rows, key=lambda r: abs(r[0] - t)) for t in (5e-6, 15e-6, 25e-6, 35e-6)]
            if not (samples[0][1] >= 2 and samples[0][2] <= .8):
                raise ValueError('High WR fails to assert serial clock sink')
            for r in (samples[1], samples[3]):
                if not (0 < r[1] <= .8 and r[2] >= 2 and r[3] > 0):
                    raise ValueError('Low WR or input-bias loading absent')
                if abs(r[3] - r[1] / report['wrCircuit']['lowOhms']) > 1e-9:
                    raise ValueError('WR current violates fixture endpoint resistance')
            if abs(samples[2][3]) > 1e-12 or abs(samples[2][4]) > 1e-12:
                raise ValueError('Released CPU output still drives WR')
            report['runs'].append({'stepNs': step, 'signals': signals.split(), 'samples': samples,
                                   'files': {p.name: sha(p) for p in run.iterdir()}})
        a, b = (r['samples'] for r in report['runs'])
        dv = max(abs(x[i]-y[i]) for x,y in zip(a,b) for i in (1,2))
        di = max(abs(x[i]-y[i]) for x,y in zip(a,b) for i in (3,4,5))
        report['comparison'] = {'maximumSampleVoltageDifference': dv, 'maximumSampleCurrentDifferenceAmps': di,
                                'budgets': {'sampleVolts': .001, 'sampleAmps': 1e-6},
                                'boundary': 'Settled-state sample convergence, not transition timing'}
        if dv > .001 or di > 1e-6:
            raise ValueError('WR samples fail timestep refinement')
        if sha(executable) != report['executableSha256']:
            raise ValueError('Simulator changed during fixture')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(out / 'report.json')


if __name__ == '__main__':
    main()
