#!/usr/bin/env python3
"""Observe a failed service driver without changing its circuit or numerical controls."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess

from failure_evidence import solver_diagnostic
from ngspice_runtime import identify, verify


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--all-drivers', action='store_true',
                        help='Also record LED and column DAC outputs for analog-only replay')
    args = parser.parse_args()
    source, out = args.source.resolve(), args.out.resolve()
    original = json.loads((source / 'report.json').read_text())
    assumptions = original['assumptions']
    if (original.get('passed') is not False or not assumptions.get('hostBuffer')
            or assumptions.get('serialDriver') != '7406-dc'
            or assumptions.get('electricalBus') or assumptions.get('cpuProfile') != 'tv80'):
        raise ValueError('Expected a failed TV80 service host capture with the transistor serial driver')
    if sha(source / 'io.cir') != original['deckSha256']:
        raise ValueError('Source deck differs from its producer report')
    if sha(source / 'ngspice.log') != original['failureArtifacts']['ngspice.log']['sha256']:
        raise ValueError('Source failure log differs from its producer report')
    expected_diagnostic = solver_diagnostic((source / 'ngspice.log').read_text())
    if not expected_diagnostic:
        raise ValueError('Source has no solver failure to replay')
    for name, digest in original['hdlSha256'].items():
        if sha(name) != digest:
            raise ValueError('HDL source differs: ' + name)
    for library in original['bridge']['libraries'].values():
        if sha(library['path']) != library['sha256']:
            raise ValueError('Bridge library differs')
    rom = bytes(int(value, 16) for value in (source / 's600.hex').read_text().split())
    if hashlib.sha256(rom).hexdigest() != original['romSha256']:
        raise ValueError('ROM differs from source capture')
    runtime, env = identify(original['ngspiceRuntime']['executable']['path'],
                            original['ngspiceRuntime']['spinit']['path'])
    if runtime != original['ngspiceRuntime']:
        raise ValueError('Runtime differs from source capture')
    compiler = subprocess.run(['iverilog', '-V'], capture_output=True, text=True, check=True).stdout.splitlines()[0]
    if compiler != original['iverilog']:
        raise ValueError('HDL compiler version differs from source capture')
    out.mkdir(parents=True, exist_ok=False)
    report = {'qualified': False, 'scope': __doc__, 'reproducedFailure': False,
              'sourceReportSha256': sha(source / 'report.json'),
              'sourceDirectory': str(source), 'ngspiceRuntime': runtime,
              'validationSources': {name: sha(Path(__file__).parent / name) for name in
                                    ('driver_boundary_replay.py', 'failure_evidence.py', 'ngspice_runtime.py')},
              'boundary': 'Diagnostic replay, not scenario acceptance. Trailing rows from an aborted solve may be rejected trial states.'}
    try:
        top = 'firmware_io_cosim'
        command = ['iverilog', '-g2012', '-s', top, '-o', str(out / 'io.vvp'),
                   f'-P{top}.HOST_BUFFER=1',
                   f'-P{top}.ELECTRICAL_CPU_PULLUPS={int(assumptions["electricalCpuPullups"])}',
                   f'-P{top}.ELECTRICAL_LOGIC_PULLUPS={int(assumptions["electricalLogicPullups"])}',
                   *original['hdlSha256']]
        subprocess.run(command, check=True)
        report['compileCommand'] = command
        report['compiledHdlSha256'] = sha(out / 'io.vvp')
        # Icarus embeds process-dependent labels. Verify source hashes, flags
        # and compiler, then require byte-identical original voltage waveforms.
        report['originalCompiledHdlSha256'] = sha(source / 'io.vvp')
        report['hdlSources'] = original['hdlSha256']
        report['iverilog'] = compiler
        shutil.copyfile(source / 's600.hex', out / 's600.hex')
        signals = ['v(data_intent)', 'v(clock_intent)', 'v(n_TA_DATEN)',
                   'v(n_p5V)', 'i(L1.4)', 'v(xdata.output_base)']
        if args.all_drivers:
            signals += ['v(led0_v)', 'v(led1_v)', *[f'v(sink{i})' for i in range(13)]]
        report['allDrivers'] = args.all_drivers
        deck = (source / 'io.cir').read_text()
        if deck.count('\n.control\n') != 1 or deck.count('\nquit\n') != 1:
            raise ValueError('Expected one control block and quit command')
        deck = deck.replace('\n.control\n', '\n.save ' + ' '.join(signals) + '\n.control\n')
        deck = deck.replace('\nquit\n', '\nwrdata boundary-trace.txt ' + ' '.join(signals) + '\nquit\n')
        (out / 'io.cir').write_text(deck)
        report['signals'] = signals
        report['deckSha256'] = sha(out / 'io.cir')
        verify(runtime)
        with (out / 'ngspice.log').open('w') as log:
            process = subprocess.run([runtime['executable']['path'], '-n', '-b', 'io.cir'],
                                     cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=600)
        verify(runtime)
        report['exitCode'] = process.returncode
        report['solverDiagnostic'] = solver_diagnostic((out / 'ngspice.log').read_text())
        report['originalWaveformIdentities'] = {}
        for name in ('trace.txt', 'host-trace.txt', 'driver-trace.txt'):
            digest = sha(out / name)
            if digest != original['compressedWaveforms'][name]['sha256']:
                raise ValueError('Added observation changed original waveform: ' + name)
            report['originalWaveformIdentities'][name] = digest
        if report['solverDiagnostic'] != expected_diagnostic:
            raise ValueError('Original solver diagnostic did not recur')
        count, previous = 0, None
        with (out / 'boundary-trace.txt').open() as stream:
            if stream.readline().split() != ['time', *signals]:
                raise ValueError('Boundary trace header differs')
            for line in stream:
                row = list(map(float, line.split()))
                if (len(row) != len(signals) + 1 or not all(map(math.isfinite, row))
                        or (previous is not None and row[0] < previous)):
                    raise ValueError('Malformed boundary trace')
                previous = row[0]
                count += 1
        if not count:
            raise ValueError('Empty boundary trace')
        report['boundaryRows'] = count
        report['lastSampleSeconds'] = previous
        report['reproducedFailure'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        report['artifacts'] = {name: sha(out / name) for name in
                               ('io.cir', 'ngspice.log', 'boundary-trace.txt') if (out / name).exists()}
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(out / 'report.json')


if __name__ == '__main__':
    main()
