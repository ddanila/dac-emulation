#!/usr/bin/env python3
"""Qualify reset/restart, serial timing and receiver margins of full-board scenario pairs."""
import argparse
import copy
import hashlib
import json
import math
import re
from pathlib import Path

from boot_cosim import validate, sha
from receiver_margins import measure
from clock_convergence import compare_clocks

HERE = Path(__file__).resolve().parent


def load_run(directory):
    report = json.loads((directory / 'report.json').read_text())
    if report.get('passed') is not True or report.get('preparedOnly'):
        raise ValueError('Full-board run did not pass: ' + str(directory))
    if not report.get('scenario') or not all(report['assumptions'].get(key) for key in
                                            ('electricalMatrix', 'electricalOutputs', 'serialReceiver')):
        raise ValueError('Expected a full-board electrical contact scenario')
    for name, key in [('boot.cir', 'deckSha256'), ('ngspice.log', 'logSha256'), ('trace.txt', 'traceSha256')]:
        if sha(directory / name) != report[key]:
            raise ValueError('Retained artifact hash differs: ' + name)
    gate = report.get('gateModel', {'file': 'ls_nand_nominal.cir',
                                     'sha256': report['sources'].get('ls_nand_nominal.cir')})
    expected_gate = 'ls_nand_dc.cir' if report['assumptions'].get('gateProfile') == 'dl000-dc' else 'ls_nand_nominal.cir'
    if gate['file'] != expected_gate or gate['sha256'] != report['sources'][expected_gate] or sha(directory / expected_gate) != gate['sha256']:
        raise ValueError('Retained oscillator gate model differs')
    deck = (directory / 'boot.cir').read_text()
    if re.findall(r'^\.include (\S+)$', deck, re.M) != [expected_gate]:
        raise ValueError('Executed oscillator model include differs')
    steps = re.findall(r'^tran ([0-9.eE+-]+)n ', deck, re.M)
    if len(steps) != 1 or float(steps[0]) != report['assumptions']['maximumStepNs']:
        raise ValueError('Reported timestep differs from executed deck')
    if json.loads((directory / 'scenario.json').read_text()) != report['scenario']:
        raise ValueError('Retained contact recipe differs')
    rom = bytes(int(value, 16) for value in (directory / 's600.hex').read_text().split())
    if hashlib.sha256(rom).hexdigest() != report['romSha256']:
        raise ValueError('Retained ROM differs')
    checked = copy.deepcopy(report)
    validate(directory, checked)
    for key in ('resetEvents', 'firstFetchAfterRelease', 'serialTransport', 'scenarioCoverage'):
        if json.loads(json.dumps(checked[key])) != report[key]:
            raise ValueError('Retained observations differ from report: ' + key)
    return report, re.sub(r'^tran \S+ ', 'tran TIMESTEP ', deck, flags=re.M)


def compare(coarse, fine, tolerance_ns):
    if not 0 < fine['assumptions']['maximumStepNs'] <= coarse['assumptions']['maximumStepNs'] / 2:
        raise ValueError('Expected at least a halved timestep')
    assumptions = [{k: v for k, v in r['assumptions'].items() if k not in ('maximumStepNs', 'timeoutSeconds')}
                   for r in (coarse, fine)]
    if assumptions[0] != assumptions[1]:
        raise ValueError('Full-board assumptions differ')
    for key in ('romSha256', 'connectivitySha256', 'bridge', 'tv80', 'ngspice', 'iverilog', 'scenario', 'sources'):
        if coarse[key] != fine[key]:
            raise ValueError('Full-board provenance differs: ' + key)
    def hdl(report):
        files = {Path(name).name: digest for name, digest in report['hdlSha256'].items()}
        if len(files) != len(report['hdlSha256']):
            raise ValueError('Ambiguous HDL input names')
        return files
    if hdl(coarse) != hdl(fine):
        raise ValueError('Compiled HDL inputs differ')
    differences = {}
    for kind in ('transmitted', 'received'):
        a, b = coarse['serialTransport'][kind], fine['serialTransport'][kind]
        if not a or [bit for _, bit in a] != [bit for _, bit in b]:
            raise ValueError('Serial sequence changes with timestep: ' + kind)
        differences[kind + 'MaximumDifferenceNs'] = max(abs(x[0] - y[0]) / 1000 for x, y in zip(a, b))
    for key in ('resetEvents',):
        a, b = coarse[key], fine[key]
        if not a or [v for _, v in a] != [v for _, v in b]:
            raise ValueError('Reset sequence changes with timestep')
        differences['resetMaximumDifferenceNs'] = max(abs(x[0] - y[0]) * 1e9 for x, y in zip(a, b))
    a, b = coarse['firstFetchAfterRelease'], fine['firstFetchAfterRelease']
    if a[1:] != b[1:]:
        raise ValueError('First instruction fetch differs')
    differences['firstFetchDifferenceNs'] = abs(a[0] - b[0]) * 1e9
    return {'differences': differences, 'withinTolerance': all(v <= tolerance_ns for v in differences.values())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('coarse', type=Path)
    parser.add_argument('fine', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--tolerance-ns', type=float, default=15)
    parser.add_argument('--required-margin-ns', type=float, default=100)
    args = parser.parse_args()
    if any(not math.isfinite(v) or v <= 0 for v in (args.tolerance_ns, args.required_margin_ns)):
        parser.error('Timing budgets must be positive and finite')
    result = {'passed': False, 'scope': __doc__, 'toleranceNs': args.tolerance_ns,
              'boundary': 'Selected nominal board scenario; no device calibration, C equivalence, brownout or full waveform-shape claim',
              'sources': {name: sha(HERE / name) for name in ('qualify_board_pair.py', 'boot_cosim.py',
                          'board_scenario.py', 'io_scenario.py', 'receiver_margins.py', 'serial_observation.py', 'clock_convergence.py', 'trace_io.py')}}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    try:
        result['inputs'] = {name: {'path': str(path.resolve()), 'reportSha256': sha(path / 'report.json')}
                           for name, path in [('coarse', args.coarse), ('fine', args.fine)]}
        coarse, cd = load_run(args.coarse)
        fine, fd = load_run(args.fine)
        if cd != fd:
            raise ValueError('Electrical decks differ beyond timestep')
        result['clockConvergence'] = compare_clocks(
            args.coarse / 'trace.txt', args.fine / 'trace.txt',
            coarse['assumptions']['maximumStepNs'], fine['assumptions']['maximumStepNs'], args.tolerance_ns)
        if not result['clockConvergence']['passed']:
            raise ValueError('Electrical clock phase or sampled extrema do not converge within budget')
        result['comparison'] = compare(coarse, fine, args.tolerance_ns)
        if not result['comparison']['withinTolerance']:
            raise ValueError('Full-board timing differs beyond the declared budget')
        result['margins'] = {}
        for name, path, report in [('coarse', args.coarse, coarse), ('fine', args.fine, fine)]:
            margins = measure(path / 'trace.txt', report['serialTransport']['received'],
                              report['assumptions']['maximumStepNs'], args.required_margin_ns,
                              columns=5, data_column=3)
            result['margins'][name] = margins
            if not margins['withinBudget']:
                raise ValueError('Receiver margins fail: ' + name)
            if sha(path / 'report.json') != result['inputs'][name]['reportSha256']:
                raise ValueError('Input report changed during qualification')
        result['passed'] = True
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(args.out)


if __name__ == '__main__':
    main()
