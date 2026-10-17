#!/usr/bin/env python3
"""Compare retained electrical LED intent sequences with an instrumented C replay."""
import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

from compare_firmware_io import sha
from trace_io import open_text

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def intent_events(path, start_seconds=.001):
    result = []
    previous_time = None
    with open_text(path) as stream:
        next(stream)
        for line in stream:
            row = [float(x) for x in line.split()]
            if len(row) != 5 or not all(map(math.isfinite, row)):
                raise ValueError('Invalid LED waveform')
            stamp = row[0]
            if previous_time is not None and stamp < previous_time:
                raise ValueError('LED waveform time reversal')
            previous_time = stamp
            if stamp < start_seconds:
                continue
            bits = [0 if v < .8 else 1 if v > 4.2 else None for v in row[1:3]]
            # DAC transitions pass through intermediate voltages. The separate
            # electrical check rejects persistent unknowns and checks currents.
            if None in bits:
                continue
            state = bits[0] | (bits[1] << 1)
            if not result or result[-1][1] != state:
                result.append([stamp, state])
    if not result:
        raise ValueError('No known LED states after reset release')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory', type=Path)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    report_path = args.out if args.out.suffix == '.json' else args.out / 'comparison.json'
    if args.out.suffix == '.json':
        args.out = args.out.with_suffix('')
    args.out.mkdir(parents=True, exist_ok=True)
    result = {'passed': False, 'scope': __doc__,
              'timingScope': 'Ordinal LED states only; C cycles and electrical seconds are not phase-aligned',
              'sources': {name: sha(HERE / name) for name in
                          ('compare_led_reference.py', 'firmware_io_reference.c', 'trace_io.py')}}
    try:
        original = json.loads((args.directory / 'report.json').read_text())
        result['originalReportSha256'] = sha(args.directory / 'report.json')
        if original.get('passed') is not True or not original.get('ledObservation', {}).get('passed'):
            raise ValueError('Expected a completed run with passing electrical LED observations')
        if sha(args.directory / 'led-trace.txt') != original['ledTraceSha256']:
            raise ValueError('Retained LED trace differs')
        header = args.directory / 'io_scenario.h'
        if sha(header) != original['generatedScenarioHeaderSha256']:
            raise ValueError('Retained scenario header differs')
        # Instrumentation changes the driver output only. All emulation sources
        # and headers must still match those used by the original serial oracle.
        for name, digest in original['cReferenceSources'].items():
            if Path(name).name != 'firmware_io_reference.c' and sha(Path(name)) != digest:
                raise ValueError('C emulator source differs from original run: ' + name)
        rom = bytes(int(x, 16) for x in (args.directory / 's600.hex').read_text().split())
        if hashlib.sha256(rom).hexdigest() != original['romSha256']:
            raise ValueError('Retained ROM differs')
        (args.out / 's600.bin').write_bytes(rom)
        binary = args.out / 'reference'
        subprocess.run(['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-DOBSERVE_LEDS',
                        '-I', str(args.directory), str(HERE / 'firmware_io_reference.c'),
                        str(ROOT / 'machines/robotron1715m/keyboard.c'), str(ROOT / 'common/cpu/z80.c'),
                        '-o', str(binary)], check=True)
        log = subprocess.check_output([str(binary.resolve()), str((args.out / 's600.bin').resolve())], text=True)
        (args.out / 'reference.log').write_text(log)
        result['referenceLogSha256'] = sha(args.out / 'reference.log')
        if sha(args.directory / 'reference.log') != original['referenceLogSha256']:
            raise ValueError('Original C serial reference differs')
        if re.findall(r'^BIT .+$', log, re.M) != re.findall(r'^BIT .+$', (args.directory / 'reference.log').read_text(), re.M):
            raise ValueError('Instrumented C replay changed serial observations')
        c = [[int(t), int(v)] for t, v in re.findall(r'^LED (\d+) ([0-3])$', log, re.M)]
        electrical = intent_events(args.directory / 'led-trace.txt')
        result['cEvents'] = c
        result['electricalEvents'] = electrical
        states_c, states_e = [v for _, v in c], [v for _, v in electrical]
        result['firstDifference'] = next(({'signal': 'LED intent state', 'ordinal': i, 'c': c[i] if i < len(c) else None,
                                           'electrical': electrical[i] if i < len(electrical) else None}
                                          for i in range(max(len(c), len(electrical)))
                                          if i >= len(c) or i >= len(electrical) or states_c[i] != states_e[i]), None)
        if not c or result['firstDifference'] is not None:
            raise ValueError('LED intent sequence differs from C reference')
        if sha(args.directory / 'report.json') != result['originalReportSha256']:
            raise ValueError('Original report changed during comparison')
        result['passed'] = True
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        report_path.write_text(json.dumps(result, indent=2) + '\n')
    print(report_path)


if __name__ == '__main__':
    main()
