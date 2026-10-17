#!/usr/bin/env python3
"""Check early clock phase in the coupled board; does not qualify boot or firmware."""
import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

from boot_cosim import sha
from clock_convergence import compare_clocks
from failure_evidence import capture, solver_diagnostic

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DIAGNOSTIC_SIGNALS = ('v(n_p5V)', 'v(n_OSC_RC)', 'v(n_OSC1)', 'v(n_OSC2)',
                      'v(n_OSC_OUT)', 'v(n_CABLE_GND)', 'i(Vhost)')


def early_deck(deck, step_ns, duration_us, diagnostics=()):
    """Keep the prepared circuit intact and save startup instead of the boot tail."""
    matches = re.findall(r'^tran ([0-9.eE+-]+)n ([0-9.eE+-]+) 124m$', deck, re.M)
    if len(matches) != 1 or float(matches[0][0]) != step_ns:
        raise ValueError('Unexpected prepared transient command')
    if diagnostics:
        if len(re.findall(r'^\.save .+$', deck, re.M)) != 1 or len(re.findall(r'^wrdata trace.txt .+$', deck, re.M)) != 1:
            raise ValueError('Unexpected prepared waveform commands')
        deck = re.sub(r'^(\.save .+)$', lambda m: m[0] + ' ' + ' '.join(diagnostics), deck, flags=re.M)
        deck = re.sub(r'^(wrdata trace.txt .+)$', lambda m: m[0] + '\nwrdata diagnostic-trace.txt ' + ' '.join(diagnostics), deck, flags=re.M)
    return re.sub(r'^tran [0-9.eE+-]+n [0-9.eE+-]+ 124m$',
                  f'tran {step_ns}n {duration_us}u', deck, flags=re.M)


def run(args, step, directory):
    directory.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(HERE / 'boot_cosim.py'), '--rom', str(args.rom.resolve()),
               '--out', str(directory), '--prepare-only', '--electrical-matrix', '--electrical-outputs',
               '--step-ns', str(step), '--gate-profile', args.gate_profile,
               '--column-load-pf', str(args.column_load_pf), '--rise-us', str(args.rise_us),
               '--reltol', str(args.reltol), '--vntol', str(args.vntol), '--abstol', str(args.abstol)]
    subprocess.run(command, check=True, capture_output=True, text=True, timeout=60)
    prepared = json.loads((directory / 'report.json').read_text())
    if prepared['passed'] or not prepared.get('preparedOnly') or sha(directory / 'boot.cir') != prepared['deckSha256']:
        raise ValueError('Invalid prepared board inputs')
    deck = early_deck((directory / 'boot.cir').read_text(), step, args.duration_us, DIAGNOSTIC_SIGNALS)
    (directory / 'clock-probe.cir').write_text(deck)
    (directory / 'diagnostic-trace.txt').unlink(missing_ok=True)
    result = {'completed': False, 'stepNs': step, 'preparedBoard': prepared,
              'preparedReportSha256': sha(directory / 'report.json'),
              'probeDeckSha256': sha(directory / 'clock-probe.cir')}
    try:
        with (directory / 'ngspice.log').open('w') as log:
            subprocess.run(['ngspice', '-n', '-b', 'clock-probe.cir'], cwd=directory,
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=args.timeout_seconds)
        result['logSha256'] = sha(directory / 'ngspice.log')
        log = (directory / 'ngspice.log').read_text()
        diagnostic = solver_diagnostic(log)
        if diagnostic:
            result['solverDiagnostic'] = diagnostic
            raise ValueError('Coupled clock solver/HDL diagnostics: ' + diagnostic)
        result['traceSha256'] = sha(directory / 'trace.txt')
        result['diagnosticTraceSha256'] = sha(directory / 'diagnostic-trace.txt')
        result['diagnosticSignals'] = summarize_diagnostics(directory / 'diagnostic-trace.txt', args.duration_us)
        result['completed'] = True
    except Exception as error:
        result['error'] = str(error)
        result['failureArtifacts'] = capture(directory, ('ngspice.log', 'trace.txt', 'diagnostic-trace.txt'))
        raise
    finally:
        (directory / 'clock-probe.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def summarize_diagnostics(path, duration_us):
    ranges = {name: {'minimum': math.inf, 'maximum': -math.inf} for name in DIAGNOSTIC_SIGNALS}
    first, last = None, None
    with path.open() as stream:
        next(stream)
        for line in stream:
            row = list(map(float, line.split()))
            if len(row) != len(DIAGNOSTIC_SIGNALS) + 1 or not all(map(math.isfinite, row)):
                raise ValueError('Invalid diagnostic waveform')
            if last is not None and row[0] < last:
                raise ValueError('Diagnostic waveform time reverses')
            first = row[0] if first is None else first
            last = row[0]
            for name, value in zip(DIAGNOSTIC_SIGNALS, row[1:]):
                ranges[name]['minimum'] = min(ranges[name]['minimum'], value)
                ranges[name]['maximum'] = max(ranges[name]['maximum'], value)
                ranges[name]['final'] = value
    if first is None or first > 1e-9 or abs(last - duration_us * 1e-6) > 1e-12:
        raise ValueError('Incomplete diagnostic waveform')
    return {'firstSeconds': first, 'lastSeconds': last, 'ranges': ranges,
            'units': 'Volts for v(...), amperes for i(...); source current uses SPICE sign convention'}


def matching_inputs(coarse, fine):
    for key in ('romSha256', 'connectivitySha256', 'bridge', 'tv80', 'ngspice', 'iverilog', 'sources'):
        if coarse[key] != fine[key]:
            raise ValueError('Prepared board inputs differ: ' + key)
    assumptions = [{k: v for k, v in r['assumptions'].items() if k != 'maximumStepNs'} for r in (coarse, fine)]
    if assumptions[0] != assumptions[1]:
        raise ValueError('Prepared board assumptions differ')
    hdl = []
    for report in (coarse, fine):
        by_name = {Path(path).name: digest for path, digest in report['hdlSha256'].items()}
        if len(by_name) != len(report['hdlSha256']):
            raise ValueError('Ambiguous prepared HDL filenames')
        hdl.append(by_name)
    if hdl[0] != hdl[1]:
        raise ValueError('Prepared board HDL differs')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-analog/coupled-clock-probe')
    parser.add_argument('--steps-ns', type=float, nargs=2, default=(1, .5))
    parser.add_argument('--duration-us', type=float, default=1000)
    parser.add_argument('--timeout-seconds', type=float, default=1200)
    parser.add_argument('--gate-profile', choices=('nominal', 'dl000-dc'), default='nominal')
    parser.add_argument('--column-load-pf', type=float, default=0, help='Assumed fixture capacitance per column to ground')
    parser.add_argument('--rise-us', type=float, default=1)
    parser.add_argument('--reltol', type=float, default=1e-7)
    parser.add_argument('--vntol', type=float, default=1e-9)
    parser.add_argument('--abstol', type=float, default=1e-15)
    args = parser.parse_args()
    if not math.isfinite(args.column_load_pf) or args.column_load_pf < 0:
        parser.error('column-load-pf must be finite and nonnegative')
    if any(not math.isfinite(v) or v <= 0 for v in (*args.steps_ns, args.duration_us, args.timeout_seconds,
                                                  args.rise_us, args.reltol, args.vntol, args.abstol)):
        parser.error('Timesteps, duration and solver tolerances must be positive and finite')
    if args.steps_ns[0] > 10 or args.steps_ns[1] > args.steps_ns[0] / 2:
        parser.error('Coarse step must be at most 10 ns and fine at most half coarse')
    if not 10 <= args.duration_us <= 10000:
        parser.error('Early clock probe duration must be between 10 and 10000 us')
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    report = {'passed': False, 'scope': __doc__, 'durationUs': args.duration_us, 'runs': [],
              'qualificationBoundary': 'Early startup only, before normal reset release; no full-boot, firmware or long-duration phase qualification',
              'sources': {name: sha(HERE / name) for name in (
                  'coupled_clock_probe.py', 'boot_cosim.py', 'clock_convergence.py', 'failure_evidence.py', 'trace_io.py')}}
    try:
        for label, step in zip(('coarse', 'fine'), args.steps_ns):
            report['runs'].append(run(args, step, args.out / label))
        matching_inputs(*(r['preparedBoard'] for r in report['runs']))
        phase = compare_clocks(args.out / 'coarse/trace.txt', args.out / 'fine/trace.txt', *args.steps_ns)
        report['clockPhase'] = phase
        for waveform in phase['waveforms'].values():
            if waveform['firstSampleSeconds'] > 1e-9 or abs(waveform['lastSampleSeconds'] - args.duration_us * 1e-6) > 1e-12:
                raise ValueError('Incomplete early clock waveform')
        if not phase['passed']:
            raise ValueError('Early coupled clock fails phase refinement')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (args.out / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(args.out / 'qualification.json')


if __name__ == '__main__':
    main()
