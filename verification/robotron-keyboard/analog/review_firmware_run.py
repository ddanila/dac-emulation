"""Diagnose retained failed firmware bus runs without reexecuting SPICE."""
from pathlib import Path
import argparse
import hashlib
import json
import re
from bus_observation import measure, BusMismatch
from serial_observation import validate_transport, first_reference_difference
from trace_io import open_text
from io_scenario import time_ns
HERE = Path(__file__).resolve().parent

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    root = args.run
    rom = args.rom.read_bytes()
    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    report = json.loads((root / 'report.json').read_text())
    log = (root / 'ngspice.log').read_text()
    reference = (root / 'reference.log').read_text()
    if hashlib.sha256(rom).hexdigest() != report['romSha256']:
        raise ValueError('ROM hash differs')
    if sha(root / 'reference.log') != report['referenceLogSha256']:
        raise ValueError('Reference hash differs')
    if sha(root / 'scenario.json') != report['scenarioSha256']:
        raise ValueError('Scenario hash differs')
    scenario = json.loads((root / 'scenario.json').read_text())
    for name in ('ngspice.log', 'bus-trace.txt.xz'):
        if sha(root / name) != report['failureArtifacts'][name]['sha256']:
            raise ValueError('Artifact hash differs: ' + name)
    result = {'qualified': False, 'originalPassed': report['passed'], 'originalError': report.get('error'), 'originalBusFailure': report.get('busFailure'), 'inputHashes': {name: sha(root / name) for name in ('report.json', 'ngspice.log', 'reference.log', 'bus-trace.txt.xz')}, 'reviewScriptSha256': sha(Path(__file__)), 'checkerSources': {name: sha(HERE / name) for name in ('bus_observation.py', 'cpu_clock_limits.json', 'serial_observation.py', 'trace_io.py', 'io_scenario.py')}}
    try:
        result['busObservation'] = measure(log, root / 'bus-trace.txt', report['assumptions']['stepNs'], rom, trace_extent=(0, time_ns(scenario['cycles']) * 1e-09))
    except (ValueError, BusMismatch) as error:
        result['recheckedError'] = str(error)
        result['recheckedBusFailure'] = getattr(error, 'details', None)
    reference_events = [(int(c), int(b)) for (c, b) in re.findall('^BIT (\\d+) ([01])$', reference, re.M)]
    if not reference_events:
        raise ValueError('Reference has no serial bits')
    try:
        transport = validate_transport(log, require_activity=True)
        result['serialTransport'] = transport
        result['firstSerialDifference'] = first_reference_difference(reference_events, transport['received'])
        result['serialBitsMatchC'] = result['firstSerialDifference'] is None
    except ValueError as error:
        result['serialError'] = str(error)
    samples = [x for x in log.splitlines() if x.startswith('BUS_SAMPLE ')]
    unknown = [x for x in samples if len(x.split()) == 7 and re.search('[xXzZ]', x.split()[3])]
    result['unknownReads'] = {'count': len(unknown), 'firstExamples': unknown[:3]}
    failure = result.get('recheckedBusFailure') or result.get('originalBusFailure')
    if failure:
        stamp = failure['readTimePs'] * 1e-12
        window = [stamp - 1e-07, stamp + 1e-07]
        retained = []
        with open_text(root / 'bus-trace.txt') as f:
            header = next(f)
            for line in f:
                t = float(line.split()[0])
                if t > window[1]:
                    break
                if t >= window[0]:
                    retained.append(line)
        (out / 'first-read-window.txt').write_text(header + ''.join(retained))
        result['windowSeconds'] = window
        result['windowSha256'] = sha(out / 'first-read-window.txt')
    result['boundary'] = 'Post-run diagnosis only. Original failure is retained. Serial bit agreement does not qualify the electrical bus; waveform excerpt cannot reproduce a full-run gate.'
    result['reviewCompleted'] = True
    (out / 'assessment.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result.get(k) for k in ('recheckedError', 'recheckedBusFailure', 'serialBitsMatchC', 'unknownReads')}, indent=2))
if __name__ == '__main__':
    main()
