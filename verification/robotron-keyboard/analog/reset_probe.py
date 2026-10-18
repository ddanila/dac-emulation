#!/usr/bin/env python3
"""Run the reference reset topology with explicit exploratory device/load models."""
import argparse
import hashlib
import json
import math
import re
import subprocess
import shutil
from pathlib import Path

from circuit import elements, load, node, nominal_models
import supply_stimulus
from reset_supply_observation import observe

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RESET_REFS = ('C1', 'C2', 'C4', 'R3', 'R4.1', 'R4.2', 'R5', 'R6.1',
              'R7', 'R8', 'V1.1', 'V1.2', 'V2', 'V3.1', 'V3.2', 'V4.9')


def simulate(args, components, step_us, isolated):
    out = args.out.resolve() / f'{"isolated" if isolated else "closed"}-{step_us}us'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'trace.txt').unlink(missing_ok=True)
    lines, models = elements(components, RESET_REFS)
    bridge = components['BR2']
    if bridge['type'] != 'BRIDGE' or set(bridge['pins']) != {'1', '2'}:
        raise ValueError('Unexpected BR2 topology')
    source, cpu = [node(bridge['pins'][p]) for p in ('1', '2')]
    if cpu != node(components['A5']['pins']['26']):
        raise ValueError('BR2 no longer feeds the CPU reset pin')
    rise = args.rise_us * 1e-6
    stimulus = getattr(args, 'supply_data', None)
    stop = args.stop_seconds if stimulus else 1.6
    power = (supply_stimulus.source(stimulus, args.rise_us) if stimulus else
             f'PWL(0 0 {rise} 5 .3 5 {.3+rise} 0 1.3 0 {1.3+rise} 5 1.6 5)')
    supply = 'supply' if args.source_ohms else 'n_p5V'
    lines = ['Robotron reference reset; nominal exploratory semiconductor models',
             f'Vcc {supply} 0 {power}',
             *nominal_models(args.beta, args.npn_profile), *lines,
             f'RBR2 {source} {cpu} {"1t" if isolated else ".001"}',
             f'Rcpu {cpu} 0 1g', f'Ccpu {cpu} 0 10p']
    if args.source_ohms:
        lines += [f'Rsource supply n_p5V {args.source_ohms}']
    if isolated:
        lines += [f'Rfixture {cpu} 0 100']
    signals = ['n_p5V', source, cpu, 'n_RESET_RC', 'n_RESET_BIAS', 'n_RESET_BASE']
    lines += ['.control', 'set numdgt=17', 'set wr_singlescale', 'set wr_vecnames',
              f'tran {step_us}u {stop:.17g} 0 {step_us}u', 'wrdata trace.txt ' + ' '.join(f'v({n})' for n in signals) + ' i(Vcc)',
              'quit', '.endc', '.end']
    signals += ['supplyCurrentAmps']
    deck = '\n'.join(lines) + '\n'
    (out / 'reset.cir').write_text(deck)
    proc = subprocess.run([args.ngspice, '-n', '-b', 'reset.cir'], cwd=out,
                          capture_output=True, text=True, timeout=60)
    log = proc.stdout + proc.stderr
    (out / 'ngspice.log').write_text(log)
    proc.check_returncode()
    if re.search(r'warning|error|failed|singular', log, re.I):
        raise ValueError('Solver diagnostics: ' + str(out / 'ngspice.log'))
    rows = [[float(x) for x in line.split()] for line in (out / 'trace.txt').read_text().splitlines()[1:]]
    if not rows or any(len(r) != len(signals) + 1 or not all(map(math.isfinite, r)) for r in rows):
        raise ValueError('Incomplete/invalid reset waveform')
    if rows[0][0] > rise or rows[-1][0] < stop - 4 * math.ulp(stop):
        raise ValueError('Reset transient endpoints missing')
    if stimulus:
        return {'stepUs': step_us, 'br2Closed': not isolated,
                'observation': observe(rows, stimulus),
                'models': {**models, 'BR2': '1 milliohm closed / 1 teraohm open'},
                'signals': signals,
                'artifacts': {name: hashlib.sha256((out/name).read_bytes()).hexdigest()
                              for name in ('reset.cir', 'trace.txt', 'ngspice.log')}}
    boots = []
    for start in (0, 1.3):
        low_window = [r for r in rows if start + rise + .001 <= r[0] <= start + .05]
        high_window = [r for r in rows if start + .25 <= r[0] <= start + .29]
        if not low_window or not high_window:
            raise ValueError('Reset observation window missing')
        if max(r[2] for r in low_window) >= .8 or min(r[2] for r in high_window) <= 2:
            raise ValueError('Reference reset did not assert/release in the exploratory observation windows')
        releases = [(a, b) for a, b in zip(rows, rows[1:])
                    if start + .05 < a[0] < start + .25 and a[2] < 2 <= b[2]]
        if len(releases) != 1:
            raise ValueError('Expected one reset release per power cycle')
        a, b = releases[0]
        release = a[0] + (2-a[2]) * (b[0]-a[0]) / (b[2]-a[2]) - start
        boots.append({'releaseSecondsAt2V': release,
                      'maximumAssertedVolts': max(r[2] for r in low_window),
                      'minimumReleasedVolts': min(r[2] for r in high_window)})
    if isolated:
        if max(abs(r[3]) for r in rows) >= .01:
            raise ValueError('Opened BR2 failed to isolate the grounded CPU reset fixture')
    elif max(abs(r[2] - r[3]) for r in rows) > .01:
        raise ValueError('Closed BR2 failed to carry reset to CPU pin')
    return {'stepUs': step_us, 'br2Closed': not isolated, 'boots': boots,
            'maximumAbsoluteSupplyCurrentAmps': max(abs(r[-1]) for r in rows),
            'models': {**models, 'BR2': '1 milliohm closed / 1 teraohm open'},
            'signals': signals, 'deckSha256': hashlib.sha256(deck.encode()).hexdigest()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ngspice', default='ngspice')
    p.add_argument('--beta', type=float, default=100)
    p.add_argument('--npn-profile', choices=('generic', 'sc236-dc'), default='generic')
    power = p.add_mutually_exclusive_group()
    power.add_argument('--rise-us', type=float, default=1)
    power.add_argument('--supply-stimulus', type=Path, help='Diagnostic supply waveform; does not run normal power-cycle qualification')
    p.add_argument('--stop-seconds', type=float, default=1.6, help='Custom supply duration; must match its final point')
    p.add_argument('--source-ohms', type=float, default=0,
                   help='External source resistance; zero retains the ideal-source baseline')
    p.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-analog/reset')
    args = p.parse_args()
    if not math.isfinite(args.beta) or args.beta <= 0 or not 0 < args.rise_us <= 10000:
        p.error('beta must be positive and finite; rise-us must be in (0, 10000]')
    if not math.isfinite(args.source_ohms) or args.source_ohms < 0:
        p.error('source-ohms must be nonnegative and finite')
    if not math.isfinite(args.stop_seconds) or args.stop_seconds <= 0:
        p.error('stop-seconds must be finite and positive')
    if not args.supply_stimulus and args.stop_seconds != 1.6:
        p.error('stop-seconds requires supply-stimulus')
    try:
        args.supply_data = supply_stimulus.load(args.supply_stimulus, args.stop_seconds) if args.supply_stimulus else None
    except (ValueError, OSError) as error:
        p.error(str(error))
    executable = shutil.which(args.ngspice)
    if not executable:
        p.error('ngspice executable not found')
    args.ngspice = str(Path(executable).resolve())
    executable_sha = hashlib.sha256(Path(args.ngspice).read_bytes()).hexdigest()
    args.out.mkdir(parents=True, exist_ok=True)
    report_path = args.out / 'report.json'
    report_path.unlink(missing_ok=True)
    report = {'passed': False, 'scope': __doc__, 'runs': [],
              'executableSha256': executable_sha,
              'assumptions': {'semiconductors': 'Selected exploratory NPN profile; generic PNP and diode; no full device qualification',
                              'beta': args.beta, 'npnProfile': args.npn_profile, 'riseUs': args.rise_us,
                              'sourceOhms': args.source_ohms,
                              'passives': 'Ideal nominal R/C values; no ESR, leakage or tolerance model',
                              'cpuLoad': '1 gigaohm and 10 pF; illustrative, not measured',
                              'supply': 'Programmed ramps and one-second interruption through selected external resistance; not a measured power supply',
                              'thresholdVolts': [.8, 2],
                              'timing': 'Observation windows test nominal behavior, not historical reset duration'},
              'sources': {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                          for name in ('reset_probe.py', 'circuit.py', 'sc236_dc.cir', 'supply_stimulus.py', 'reset_supply_observation.py', 'cpu_clock_limits.json')}}
    if args.supply_data:
        report['qualified'] = False
        report['scope'] = 'Reset response to an explicit power waveform; diagnostic only, no brownout firmware qualification'
        report['supplyStimulus'] = args.supply_data
        report['assumptions']['riseUs'] = None
        report['assumptions']['supply'] = 'Programmed custom waveform through selected source resistance; not a measured power supply'
        retained = args.out / 'supply-stimulus.json'
        retained.write_text(json.dumps(args.supply_data, indent=2) + '\n')
        report['supplyStimulusSha256'] = hashlib.sha256(retained.read_bytes()).hexdigest()
    try:
        components, report['connectivitySha256'] = load()
        report['tool'] = subprocess.check_output([args.ngspice, '--version'], text=True).strip()
        for isolated in (False, True):
            pair = [simulate(args, components, step, isolated) for step in ((10, 5) if args.supply_data else (100, 50))]
            report['runs'].extend(pair)
            if args.supply_data:
                continue
            for coarse, fine in zip(pair[0]['boots'], pair[1]['boots']):
                if abs(coarse['releaseSecondsAt2V'] - fine['releaseSecondsAt2V']) > 100e-6:
                    raise ValueError('Reset release failed timestep convergence within 100 us')
        if hashlib.sha256(Path(args.ngspice).read_bytes()).hexdigest() != executable_sha:
            raise ValueError('Simulator changed during run')
        report['completed'] = True
        report['passed'] = not bool(args.supply_data)
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        report_path.write_text(json.dumps(report, indent=2) + '\n')
    print(report_path)


if __name__ == '__main__':
    main()
