#!/usr/bin/env python3
"""Isolate startup event scheduling using the retained CPU-free circuit.

This diagnostic does not qualify firmware, device models or full-board startup.
The captured events came from the midpoint-unknown profile; the retained circuit
maps unknown DAC inputs to zero volts deliberately to isolate event effects.
"""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from compressed_output import capture
from failure_evidence import solver_diagnostic
from ngspice_runtime import identify, verify

HERE = Path(__file__).resolve().parent


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=['replay', 'omit-release', 'isolated-breakpoint'], required=True)
    parser.add_argument('--ngspice', required=True)
    parser.add_argument('--ngspice-spinit')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--timeout-seconds', type=float, default=240)
    args = parser.parse_args()
    source = HERE / 'reports/coupled-clock-startup/analog-isolation/dac-event-drive'
    original = json.loads((source / 'report.json').read_text())
    for name in ['probe.cir', 'stimulus.txt', 'ls_nand_nominal.cir']:
        if digest(source / name) != original['artifacts'][name]['sha256']:
            raise ValueError('Retained source changed: ' + name)
    runtime, env = identify(args.ngspice, args.ngspice_spinit)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    deck = (source / 'probe.cir').read_text()
    events = [line for line in (source / 'stimulus.txt').read_text().splitlines()
              if line.strip() and not line.startswith('*')]
    assert len(events) == 4
    release = Decimal(events[-1].split()[0])
    if args.case != 'replay':
        events.pop()
    if args.case == 'isolated-breakpoint':
        # No electrical connection to any board node. Both PWL knots are
        # explicit: changing the isolated source creates a solver breakpoint.
        dummy = (f'Visolated isolated_event 0 PWL(0 0 {release} 0 '
                 f'{release + Decimal("1e-9")} 1)\nRisolated isolated_event 0 1k\n')
        deck = deck.replace('.control', dummy + '.control')
    controls = ['data_intent', 'clock_intent', 'led1_v', 'led0_v'] + [f'sink{i}' for i in range(13)]
    deck = deck.replace('.control', '.save ' + ' '.join(f'v({node})' for node in controls) + '\n.control')
    commands = ['echo DAC control absolute maxima > control-peaks.txt']
    commands += [f'print vecmax(abs(v({node}))) >> control-peaks.txt' for node in controls]
    deck = deck.replace('quit\n', '\n'.join(commands) + '\nquit\n')
    (out / 'probe.cir').write_text(deck)
    (out / 'stimulus.txt').write_text('\n'.join(events) + '\n')
    shutil.copy2(source / 'ls_nand_nominal.cir', out / 'ls_nand_nominal.cir')
    report = {'completed': False, 'qualified': False, 'case': args.case,
              'scope': __doc__, 'sourceReportSha256': digest(source / 'report.json'),
              'sources': {name: digest(HERE / name) for name in
                          ['dac_event_probe.py', 'compressed_output.py', 'ngspice_runtime.py', 'failure_evidence.py']},
              'ngspiceRuntime': runtime, 'maximumStepNs': 0.0625, 'durationUs': 150,
              'releaseEventSeconds': str(release), 'retainedDirectory': str(out)}
    try:
        with capture(out, ['trace.txt']) as compressed:
            with (out / 'ngspice.log').open('w') as log:
                proc = subprocess.run([runtime['executable']['path'], '-n', '-b', 'probe.cir'],
                                      cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT,
                                      timeout=args.timeout_seconds)
        verify(runtime)
        report['compressedWaveforms'] = compressed
        report['exitCode'] = proc.returncode
        report['solverDiagnostic'] = solver_diagnostic((out / 'ngspice.log').read_text())
        endpoint = float((out / 'endpoint.txt').read_text().split('=')[-1])
        report['endpointSeconds'] = endpoint
        peaks = (out / 'control-peaks.txt').read_text().splitlines()[1:]
        values = [float(line.split('=')[-1]) for line in peaks]
        if len(values) != len(controls):
            raise ValueError('Missing DAC control observations')
        report['controlAbsoluteMaximaV'] = dict(zip(controls, values))
        report['completed'] = (proc.returncode == 0 and not report['solverDiagnostic']
                               and abs(endpoint - 150e-6) < 1e-15)
    except Exception as exc:
        report['error'] = str(exc)
    report['artifacts'] = {p.name: {'sha256': digest(p), 'bytes': p.stat().st_size}
                           for p in out.iterdir() if p.is_file()}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report.get(k) for k in ['case', 'completed', 'solverDiagnostic', 'error']}))


if __name__ == '__main__':
    main()
