#!/usr/bin/env python3
"""Check firmware I/O timestep refinement against retained inputs and observations."""
import argparse
import hashlib
import itertools
import json
import math
import re
from pathlib import Path
from trace_io import open_binary, open_text

from serial_observation import SerialMismatch, validate_transport
from led_observation import measure as measure_leds
from failure_evidence import solver_diagnostic


def sha(path):
    digest = hashlib.sha256()
    with open_binary(path) as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_run(directory):
    report = json.loads((directory / 'report.json').read_text())
    if report.get('passed') is not True:
        raise ValueError('Run did not pass: ' + str(directory))
    for filename, key in [('io.cir', 'deckSha256'), ('ngspice.log', 'logSha256'), ('trace.txt', 'traceSha256')]:
        if sha(directory / filename) != report[key]:
            raise ValueError('Retained artifact hash differs: ' + str(directory / filename))
    steps = re.findall(r'^tran ([0-9.eE+-]+)n ', (directory / 'io.cir').read_text(), re.M)
    if len(steps) != 1 or float(steps[0]) != report['assumptions']['stepNs']:
        raise ValueError('Reported timestep differs from executed deck')
    log = (directory / 'ngspice.log').read_text()
    diagnostic = solver_diagnostic(log)
    if diagnostic:
        raise ValueError('Retained solver/HDL diagnostics: ' + diagnostic)
    transport = validate_transport(log, require_activity=True)
    # JSON represents tuples as arrays; normalize before comparison.
    if json.loads(json.dumps(transport)) != report['serialTransport']:
        raise ValueError('Serial report differs from retained log')
    if 'referenceLogSha256' in report:
        if sha(directory / 'reference.log') != report['referenceLogSha256']:
            raise ValueError('C reference log hash differs')
        bits = [int(b) for b in re.findall(r'^BIT \d+ ([01])$', (directory / 'reference.log').read_text(), re.M)]
        if bits != [b for _, b in transport['received']]:
            raise ValueError('Retained C reference and receiver differ')
    if report['assumptions'].get('ledTrace'):
        if sha(directory / 'led-trace.txt') != report['ledTraceSha256']:
            raise ValueError('Retained LED waveform hash differs')
        observed = measure_leds(directory / 'led-trace.txt', report['assumptions']['stepNs'],
                                report['assumptions'].get('requireLedActivity', False), start_seconds=.001)
        if not observed['passed'] or observed != report['ledObservation']:
            raise ValueError('LED observations fail or differ from retained trace')
    return report, transport


def compare(coarse, fine, coarse_transport, fine_transport, tolerance_ns):
    if not 0 < fine['assumptions']['stepNs'] <= coarse['assumptions']['stepNs'] / 2:
        raise ValueError('Expected the second timestep to be at most half the first')
    assumptions = []
    for report in (coarse, fine):
        values = {k: v for k, v in report['assumptions'].items() if k != 'stepNs'}
        if 'scenario' in values:
            # Acceptance windows do not change the electrical stimulus. Each
            # run's coverage is qualified separately; the deck must still match.
            values['scenario'] = {k: v for k, v in values['scenario'].items() if k != 'observations'}
        assumptions.append(values)
    if assumptions[0] != assumptions[1]:
        raise ValueError('Runs use different fixture/model assumptions')
    for key in ('romSha256', 'connectivitySha256', 'bridge', 'tv80', 'ngspice', 'iverilog'):
        if coarse[key] != fine[key]:
            raise ValueError('Run provenance differs: ' + key)
    for name in ('circuit.py', 'matrix.py', 'output_circuit.py', 'controller_interface.py',
                 'boot_cosim.v', 'firmware_io_cosim.v'):
        if coarse['sources'][name] != fine['sources'][name]:
            raise ValueError('Model source differs: ' + name)
    if coarse['assumptions'].get('latchLoad', 'ideal') != 'ideal':
        if not coarse['sources'].get('latch_limits.json') or coarse['sources']['latch_limits.json'] != fine['sources'].get('latch_limits.json'):
            raise ValueError('Latch load source differs or is missing')
    def hdl_by_name(report):
        hashes = {Path(path).name: digest for path, digest in report['hdlSha256'].items()}
        if len(hashes) != len(report['hdlSha256']):
            raise ValueError('Ambiguous HDL filenames')
        return hashes
    if hdl_by_name(coarse) != hdl_by_name(fine):
        raise ValueError('Compiled HDL inputs differ')
    for key in ('cReferenceSources', 'generatedScenarioHeaderSha256'):
        if key in coarse and key in fine and coarse[key] != fine[key]:
            raise ValueError('C reference inputs differ: ' + key)
    result = {}
    violations = []

    def timing(signal, ordinal, coarse_value, fine_value, coarse_time, fine_time):
        difference = abs(coarse_value - fine_value) / 1000
        if difference > tolerance_ns:
            violations.append({'signal': signal, 'ordinal': ordinal,
                               'coarseValuePs': coarse_value, 'fineValuePs': fine_value,
                               'coarseEventTimePs': coarse_time, 'fineEventTimePs': fine_time,
                               'differenceNs': difference, 'budgetNs': tolerance_ns})
        return difference

    for kind, signal in (('transmitted', 'serial_clock_TX'), ('received', 'serial_clock_RX')):
        a, b = coarse_transport[kind], fine_transport[kind]
        for ordinal, (left, right) in enumerate(itertools.zip_longest(a, b)):
            if left is None or right is None or left[1] != right[1]:
                raise SerialMismatch('Serial sequence changes with timestep: ' + kind,
                                     {'signal': kind + '_serial_data', 'ordinal': ordinal,
                                      'coarse': {'timePs': left[0], 'bit': left[1]} if left else None,
                                      'fine': {'timePs': right[0], 'bit': right[1]} if right else None})
        result[kind + 'MaximumDifferenceNs'] = max(
            timing(signal, i, x[0], y[0], x[0], y[0]) for i, (x, y) in enumerate(zip(a, b)))
    # Derive transport delay from integer timestamps, avoiding float roundoff at the budget.
    result['transportMaximumDifferenceNs'] = max(
        timing('serial_clock_transport', i, cr[0] - ct[0], fr[0] - ft[0], cr[0], fr[0])
        for i, (ct, cr, ft, fr) in enumerate(zip(
            coarse_transport['transmitted'], coarse_transport['received'],
            fine_transport['transmitted'], fine_transport['received'])))
    result['withinTolerance'] = not violations
    result['firstTimingDifference'] = min(
        violations, key=lambda v: min(v['coarseEventTimePs'], v['fineEventTimePs'])) if violations else None
    return result


def normalized_deck(directory):
    deck = (directory / 'io.cir').read_text()
    matches = re.findall(r'^tran (\S+) (.+)$', deck, re.M)
    if len(matches) != 1:
        raise ValueError('Expected one transient analysis')
    return re.sub(r'^tran \S+ ', 'tran TIMESTEP ', deck, flags=re.M)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('coarse', type=Path)
    p.add_argument('fine', type=Path)
    p.add_argument('--tolerance-ns', type=float, default=15)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    if not math.isfinite(args.tolerance_ns) or args.tolerance_ns <= 0:
        p.error('tolerance-ns must be positive and finite')
    result = {'passed': False, 'scope': __doc__, 'toleranceNs': args.tolerance_ns,
              'interpretation': 'Exploratory numerical comparison, not a historical receiver timing specification',
              'validationSources': {name: sha(Path(__file__).resolve().parent / name) for name in
                                    ('compare_firmware_io.py', 'serial_observation.py', 'led_observation.py', 'trace_io.py')}}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    try:
        coarse, ct = load_run(args.coarse)
        fine, ft = load_run(args.fine)
        result['reports'] = {name: {'path': str(path.resolve()), 'sha256': sha(path / 'report.json')}
                             for name, path in [('coarse', args.coarse), ('fine', args.fine)]}
        if normalized_deck(args.coarse) != normalized_deck(args.fine):
            raise ValueError('Electrical decks differ beyond timestep')
        result['comparison'] = compare(coarse, fine, ct, ft, args.tolerance_ns)
        if not result['comparison']['withinTolerance']:
            raise ValueError('Serial timing does not converge within the declared tolerance')
        result['passed'] = True
    except Exception as error:
        if isinstance(error, SerialMismatch):
            result['firstDifference'] = error.details
        result['error'] = str(error)
        raise
    finally:
        args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(args.out)


if __name__ == '__main__':
    main()
