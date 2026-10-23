#!/usr/bin/env python3
"""Qualify mixed-signal transport, not the SN7406 electrical characteristics."""
import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

from failure_evidence import solver_diagnostic
from ngspice_runtime import identify, verify

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def events(path):
    names, result, time = {}, {}, 0
    for line in path.read_text().splitlines():
        if line.startswith('$var '):
            fields = line.split()
            names[fields[3]] = fields[4]
            result[fields[4]] = []
        elif line.startswith('#'):
            time = int(line[1:])
        elif line and line[0] in '01xz' and line[1:] in names:
            result[names[line[1:]]].append((time * 1e-12, line[0]))
    if '$timescale 1 ps $end' not in path.read_text():
        raise ValueError('Unexpected VCD time unit')
    return result

def run(a, bridge, step):
    out = a.out.resolve() / f'{step}ns'
    out.mkdir(parents=True, exist_ok=True)
    for name in ('trace.txt', 'events.vcd'):
        (out / name).unlink(missing_ok=True)
    libs = {key: value['path'] for key, value in bridge['libraries'].items()}
    if any('"' in path or '\n' in path for path in libs.values()):
        raise ValueError('Unsupported quote/newline in library path')
    output_stage = ('''Aout [output] [doc] null bridge
.model bridge bidi_bridge(direction=0 out_low=0 out_high=5 in_low=0.8 in_high=2)'''
                    if a.direct_z else '''Adrive [doc] [drive] dac
Bcollector output 0 I=V(output)*V(drive)/100''')
    deck = f'''Robotron 7406 analog/HDL boundary qualification
Vin input 0 PWL(0 0 1u 0 1.1u 5 2u 5 2.1u 0 3u 0)
Vcc supply 0 5
Rpull supply output 560
Cload output 0 20p
Ain [input] [din] adc
.model adc adc_bridge(in_low=0.8 in_high=2)
Ahdl [din] [doc decho] hdl
.model hdl d_cosim simulation="{libs['shim']}" sim_args=["probe.vvp"] delay=1n
+ lib_args=["{libs['libvvp']}" "{libs['vpi']}"]
{output_stage}
Aecho [decho] [echo] dac
.model dac dac_bridge(out_low=0 out_high=5 out_undef=2.5 t_rise=1n t_fall=1n)
.control
set wr_singlescale
set wr_vecnames
tran {step}n 3u
wrdata trace.txt v(input) v(output) v(echo)
eprvcd din doc decho > events.vcd
quit
.endc
.end
'''
    (out / 'probe.cir').write_text(deck)
    subprocess.run([a.iverilog, '-g2012', '-s', 'bridge_probe',
                    '-Pbridge_probe.DIRECT_Z=' + str(int(a.direct_z)), '-o', str(out / 'probe.vvp'),
                    str(HERE / 'bridge_probe.v'), str(HERE.parent / 'chips.v')], check=True)
    proc = subprocess.run([a.ngspice, '-n', '-b', 'probe.cir'], cwd=out, capture_output=True,
                          text=True, timeout=60, env=getattr(a, 'engine_env', None))
    log = proc.stdout + proc.stderr
    (out / 'ngspice.log').write_text(log)
    proc.check_returncode()
    if solver_diagnostic(log) or re.search(r'cannot', log, re.I):
        raise ValueError('Bridge diagnostics: inspect ' + str(out / 'ngspice.log'))
    rows = [[float(v) for v in line.split()] for line in (out / 'trace.txt').read_text().splitlines()[1:]]
    if not rows or any(len(r) != 4 or not all(map(math.isfinite, r)) for r in rows):
        raise ValueError('Missing/invalid waveform')
    if rows[0][0] > 1e-9 or rows[-1][0] < 3e-6:
        raise ValueError('Incomplete transient')
    samples = [min(rows, key=lambda row: abs(row[0] - t)) for t in (.5e-6, 1.5e-6, 2.5e-6)]
    for row, high in zip(samples, (False, True, False)):
        if abs(row[1] - (5 if high else 0)) > .01 or abs(row[3] - (5 if high else 0)) > .01:
            raise ValueError('Input/echo transport failed')
        if not (0 <= row[2] < .4 if high else 4.9 < row[2] < 5.1):
            raise ValueError('Open-collector startup/drive/release failed')
    ev = events(out / 'events.vcd')
    if set(ev) != {'din', 'doc', 'decho'}:
        raise ValueError('Missing co-simulation ports')
    if not any(t < .5e-6 and value == ('z' if a.direct_z else '0') for t, value in ev['doc']):
        raise ValueError('Initial release state missing')
    if not all(any(value == 'x' for _, value in ev[name]) for name in ev):
        raise ValueError('Undefined input-band propagation missing')
    latencies = []
    for t, value in ev['din']:
        if t == 0:
            continue
        matches = [ot - t for ot, ov in ev['decho'] if ot >= t and ov == value]
        if not matches or abs(min(matches) - 18e-9) > 5e-12:
            raise ValueError('HDL 17 ns + bridge 1 ns timing failed')
        latencies.append(min(matches))
    if len(latencies) != 4:
        raise ValueError('Incomplete analog threshold transitions')
    return {'stepNs': step, 'samples': samples, 'echoLatencySeconds': latencies,
            'deckSha256': sha(out / 'probe.cir')}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--direct-z', action='store_true', help='Diagnostic: direct Z/bidi_bridge path is not qualified')
    p.add_argument('--bridge', type=Path, default=ROOT / 'build/keyboard-controller-analog/bridge/bridge.json')
    p.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-analog/boundary')
    p.add_argument('--ngspice', default='ngspice')
    p.add_argument('--ngspice-spinit', type=Path, help='Fingerprint an explicit code-model runtime')
    p.add_argument('--iverilog', default='iverilog')
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    report_path = a.out / 'report.json'
    report_path.unlink(missing_ok=True)
    report = {'passed': False, 'scope': __doc__, 'assumptions': {
        'supplyVolts': 5, 'pullupOhms': 560, 'loadFarads': 20e-12,
        'thresholdVolts': [.8, 2], 'bridgeDelaySeconds': 1e-9,
        'driver': ('ngspice bidi_bridge defaults (unqualified)' if a.direct_z else
                   'explicit sink enable: 20 ohms on, open when off; X uses 40 ohms solely as an exploratory surrogate'),
        'electricalQualification': 'Transport probe only; not calibrated SN7406 characteristics'},
        'sources': {path.name: sha(path) for path in (Path(__file__), HERE / 'failure_evidence.py', HERE / 'ngspice_runtime.py', HERE / 'bridge_probe.v', HERE.parent / 'chips.v')},
        'runs': []}
    try:
        if a.ngspice_spinit:
            report['ngspiceRuntime'], a.engine_env = identify(a.ngspice, a.ngspice_spinit)
        bridge = json.loads(a.bridge.read_text())
        report['bridge'] = bridge
        for lib in bridge['libraries'].values():
            if sha(Path(lib['path'])) != lib['sha256']:
                raise ValueError('Bridge library provenance mismatch')
        report['iverilog'] = subprocess.run([a.iverilog, '-V'], capture_output=True,
                                            text=True, check=True).stdout.splitlines()[0]
        report['ngspice'] = subprocess.check_output([a.ngspice, '--version'], text=True).strip()
        for step in (2, 1):
            report['runs'].append(run(a, bridge, step))
        for first, second in zip(report['runs'][0]['samples'], report['runs'][1]['samples']):
            if max(abs(x - y) for x, y in zip(first[1:], second[1:])) > .01:
                raise ValueError('Step refinement changes endpoint voltages')
        if a.ngspice_spinit:
            verify(report['ngspiceRuntime'])
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        report_path.write_text(json.dumps(report, indent=2) + '\n')
    print(report_path)

if __name__ == '__main__':
    main()
