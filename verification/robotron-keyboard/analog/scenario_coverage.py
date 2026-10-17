#!/usr/bin/env python3
"""Check observable scenario requirements against a completed electrical run."""
import argparse
import json
import re
from pathlib import Path

from compare_firmware_io import load_run, sha
from io_scenario import load, observe


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory', type=Path)
    p.add_argument('--scenario', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    here = Path(__file__).resolve().parent
    report = {'passed': False, 'scope': __doc__, 'validationSources': {
        name: sha(here / name) for name in ('scenario_coverage.py', 'io_scenario.py',
                                          'compare_firmware_io.py', 'serial_observation.py')}}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    try:
        original, transport = load_run(args.directory)
        scenario = load(args.scenario)
        executed = json.loads((args.directory / 'scenario.json').read_text())
        if executed != original['assumptions']['scenario']:
            raise ValueError('Retained scenario differs from original execution report')
        if sha(args.directory / 'io_scenario.h') != original['generatedScenarioHeaderSha256']:
            raise ValueError('Retained C stimulus header differs')
        # Stronger observation requirements may be applied without altering the
        # executed stimulus or overwriting the original result.
        stimulus = lambda s: {k: v for k, v in s.items() if k != 'observations'}
        if stimulus(executed) != stimulus(scenario):
            raise ValueError('Requested scenario changes the executed stimulus')
        report['originalReportSha256'] = sha(args.directory / 'report.json')
        report['scenarioSha256'] = sha(args.scenario)
        report['scenario'] = scenario
        events = [(int(cycle), int(bit)) for cycle, bit in re.findall(
            r'^BIT (\d+) ([01])$', (args.directory / 'reference.log').read_text(), re.M)]
        report['referenceCoverage'] = observe(scenario, events)
        report['receiverCoverage'] = observe(scenario, transport['received'], electrical=True)
        if not report['referenceCoverage']['passed'] or not report['receiverCoverage']['passed']:
            raise ValueError('Scenario observations are not satisfied')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(args.out)


if __name__ == '__main__':
    main()
