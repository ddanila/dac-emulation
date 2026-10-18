"""Isolate oscillator startup with a prescribed recorded supply, without HDL feedback."""
import argparse
import bisect
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess

from circuit import load
from clock_convergence import compare_clocks
from failure_evidence import solver_diagnostic
from ngspice_runtime import identify, verify
from oscillator_probe import wiring
from trace_io import open_text

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def supply_samples(source, destination):
    times, volts = [], []
    digest = hashlib.sha256()
    duplicates = 0
    with open_text(source) as stream, destination.open('w') as output:
        header = next(stream)
        digest.update(header.encode())
        if header.split()[:2] != ['time', 'v(n_p5V)']:
            raise ValueError('Expected time and board supply as the first two columns')
        for line in stream:
            digest.update(line.encode())
            t, v = line.split()[:2]
            time, voltage = float(t), float(v)
            if not math.isfinite(time) or not math.isfinite(voltage):
                raise ValueError('Nonfinite supply sample')
            if times and time == times[-1]:
                if voltage != volts[-1]:
                    raise ValueError('Conflicting supply values at one printed timestamp')
                duplicates += 1
                continue
            if times and time < times[-1]:
                raise ValueError('Supply time reversal')
            times.append(time)
            volts.append(voltage)
            output.write(t + ' ' + v + '\n')
        if len(times) < 2 or times[0] != 0 or times[-1] <= 0:
            raise ValueError('Supply must start at zero and contain a positive duration')
        # Keep filesource interpolation in bounds even if the solver probes beyond
        # the final time. This extends the last value as ordinary PWL would.
        output.write(f'{2 * times[-1]:.17g} {volts[-1]:.17g}\n')
    return times, volts, {'sourceUncompressedSha256': digest.hexdigest(),
                         'identicalDuplicateSamples': duplicates,
                         'samples': len(times), 'durationSeconds': times[-1],
                         'fileSha256': sha(destination)}


def check_supply(trace, times, volts):
    maximum = 0.0
    samples = 0
    last = None
    with open_text(trace) as stream:
        if next(stream).split() != ['time', 'v(n_CLK)', 'v(n_p5V)']:
            raise ValueError('Unexpected replay waveform columns')
        for line in stream:
            time, clock, voltage = map(float, line.split())
            if not all(map(math.isfinite, (time, clock, voltage))):
                raise ValueError('Nonfinite replay sample')
            if last is None and time != 0:
                raise ValueError('Replay does not start at zero')
            if last is not None and time < last:
                raise ValueError('Replay time reversal')
            if not 0 <= time <= times[-1]:
                raise ValueError('Replay exceeds recorded supply interval')
            index = min(bisect.bisect_right(times, time) - 1, len(times) - 2)
            fraction = (time - times[index]) / (times[index + 1] - times[index])
            expected = volts[index] + fraction * (volts[index + 1] - volts[index])
            maximum = max(maximum, abs(voltage - expected))
            samples += 1
            last = time
    if last != times[-1] or maximum > 1e-12:
        raise ValueError(f'Supply replay incomplete or interpolation mismatch: {last}, {maximum}')
    return {'samplesChecked': samples, 'maximumInterpolationErrorVolts': maximum,
            'interpolationBudgetVolts': 1e-12}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True,
                        help='Logical uncompressed diagnostic trace path; .xz/.gz siblings supported')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--ngspice', required=True)
    parser.add_argument('--steps-ns', nargs=2, type=float, default=[.25, .125])
    parser.add_argument('--timeout-seconds', type=float, default=600)
    args = parser.parse_args()
    if not all(math.isfinite(x) and x > 0 for x in [*args.steps_ns, args.timeout_seconds]):
        parser.error('Steps and timeout must be positive finite numbers')
    if args.steps_ns[0] <= args.steps_ns[1]:
        parser.error('The fine timestep must be smaller than the coarse timestep')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {'qualified': False, 'completed': False, 'runs': [],
              'scope': 'Prescribed recorded supply; isolated schematic oscillator with nominal CPU load. No live HDL or supply feedback.',
              'boundary': 'All printed supply points retained with linear interpolation; duplicate identical points collapsed and final value extended. Filesource has different breakpoint scheduling and floating-point arithmetic from PWL. This is a separate diagnostic, not an exact solver replay or physical supply model.',
              'scriptSha256': sha(__file__),
              'helpers': {name: sha(HERE / name) for name in
                          ['circuit.py', 'oscillator_probe.py', 'clock_convergence.py',
                           'trace_io.py', 'ngspice_runtime.py', 'failure_evidence.py']}}
    try:
        runtime, env = identify(args.ngspice)
        report['runtime'] = runtime
        times, volts, report['supply'] = supply_samples(args.source, out / 'supply.txt')
        components, report['connectivitySha256'] = load()
        lines, _, _, _, cpu = wiring(components)
        for label, step in zip(('coarse', 'fine'), args.steps_ns):
            run = out / label
            run.mkdir()
            shutil.copyfile(HERE / 'ls_nand_pullup.cir', run / 'ls_nand_pullup.cir')
            deck = ('Recorded-supply oscillator isolation\n'
                    'Areplay [n_p5V] supply_replay\n'
                    '.model supply_replay filesource(file="../supply.txt" amplstep=false amploffset=[0] amplscale=[1])\n'
                    '.include ls_nand_pullup.cir\n'
                    '.options reltol=1e-6 vntol=1e-8 abstol=1e-14\n' + '\n'.join(lines) +
                    f'\n.control\nset wr_singlescale\nset wr_vecnames\nset numdgt=17\n'
                    f'tran {step:.17g}n {times[-1]:.17g}\n'
                    f'wrdata trace.txt v({cpu}) v(n_p5V)\nquit\n.endc\n.end\n')
            (run / 'oscillator.cir').write_text(deck)
            record = {'stepNs': step, 'deckSha256': sha(run / 'oscillator.cir'),
                      'gateModelSha256': sha(run / 'ls_nand_pullup.cir')}
            report['runs'].append(record)
            verify(runtime)
            try:
                with (run / 'ngspice.log').open('w') as log:
                    result = subprocess.run([runtime['executable']['path'], '-n', '-b', 'oscillator.cir'],
                                            cwd=run, env=env, stdout=log, stderr=subprocess.STDOUT,
                                            timeout=args.timeout_seconds)
                record['exitCode'] = result.returncode
                result.check_returncode()
            finally:
                record['logSha256'] = sha(run / 'ngspice.log')
                verify(runtime)
            diagnostic = solver_diagnostic((run / 'ngspice.log').read_text())
            if diagnostic:
                raise ValueError(diagnostic)
            record['supplyCheck'] = check_supply(run / 'trace.txt', times, volts)
            record['traceSha256'] = sha(run / 'trace.txt')
            print(label, 'completed with checked supply interpolation', flush=True)
        report['clockPhase'] = compare_clocks(out / 'coarse/trace.txt', out / 'fine/trace.txt',
                                             *args.steps_ns, columns=3)
        report['completed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'assessment.json').write_text(json.dumps(report, indent=2) + '\n')
    return 0 if report['clockPhase']['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
