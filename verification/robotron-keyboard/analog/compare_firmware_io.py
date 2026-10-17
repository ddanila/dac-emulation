#!/usr/bin/env python3
"""Check firmware I/O timestep refinement against retained inputs and observations."""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path

from serial_observation import validate_transport


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
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
    transport = validate_transport((directory / 'ngspice.log').read_text(), require_activity=True)
    # JSON represents tuples as arrays; normalize before comparison.
    if json.loads(json.dumps(transport)) != report['serialTransport']:
        raise ValueError('Serial report differs from retained log')
    if 'referenceLogSha256' in report:
        if sha(directory / 'reference.log') != report['referenceLogSha256']:
            raise ValueError('C reference log hash differs')
        bits = [int(b) for b in re.findall(r'^BIT \d+ ([01])$', (directory / 'reference.log').read_text(), re.M)]
        if bits != [b for _, b in transport['received']]:
            raise ValueError('Retained C reference and receiver differ')
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
    for kind in ('transmitted', 'received'):
        a, b = coarse_transport[kind], fine_transport[kind]
        if [v for _, v in a] != [v for _, v in b]:
            raise ValueError('Serial sequence changes with timestep: ' + kind)
        result[kind + 'MaximumDifferenceNs'] = max(abs(x[0] - y[0]) / 1000 for x, y in zip(a, b))
    result['transportMaximumDifferenceNs'] = max(abs(a - b) * 1e9 for a, b in zip(
        coarse_transport['clockTransportSeconds'], fine_transport['clockTransportSeconds']))
    result['withinTolerance'] = all(value <= tolerance_ns for value in result.values())
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
                                    ('compare_firmware_io.py', 'serial_observation.py')}}
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
        result['error'] = str(error)
        raise
    finally:
        args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(args.out)


if __name__ == '__main__':
    main()
