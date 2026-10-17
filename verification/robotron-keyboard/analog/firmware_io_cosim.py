#!/usr/bin/env python3
"""Exercise S600 matrix/cable feedback with CPU-side clock/reset service fixtures."""
import argparse
import json
import math
import re
import subprocess
from pathlib import Path

from boot_cosim import ROM_SHA256, sha
from circuit import load
from controller_interface import generate
from matrix import matrix_circuit
from output_circuit import output_circuit
from serial_observation import validate_transport
from io_scenario import load as load_scenario, contact_source, reset_source, c_header, time_ns, observe

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom', type=Path, required=True)
    p.add_argument('--scenario', type=Path, default=HERE / 'scenarios/single-press.json')
    p.add_argument('--prepare-only', action='store_true')
    p.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-analog/firmware-io')
    p.add_argument('--bridge', type=Path, default=ROOT / 'build/keyboard-controller-analog/bridge/bridge.json')
    p.add_argument('--step-ns', type=float, default=50)
    p.add_argument('--bridge-delay-ns', type=float, default=10)
    p.add_argument('--timeout-seconds', type=float, default=1800)
    args = p.parse_args()
    if not 0 < args.step_ns <= 100 or not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0:
        p.error('step-ns must be in (0, 100]; timeout-seconds must be positive and finite')
    if not 0 < args.bridge_delay_ns <= 100:
        p.error('bridge-delay-ns must be in (0, 100]')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    for name in ('report.json', 'trace.txt', 'ngspice.log'):
        (out / name).unlink(missing_ok=True)
    report = {'passed': False, 'scope': __doc__, 'assumptions': {
        'clockPeriodNs': 1000, 'resetRampStartNs': 1000000, 'fixtureEdgeNs': 1,
        'fixtureThresholdVolts': 1.4, 'br1Closed': False, 'br2Closed': False,
        'contactTransitionNs': 1,
        'supply': '1 us host-supply ramp through cable paths; fixture holds CPU reset for 1 ms; no board power-on-reset qualification',
        'semiconductors': 'Generic matrix PNP and nominal output/load models',
        'coverage': 'TV80, resolved ROM/latch bus, electrical matrix and cable receiver; oscillator/reset generators excluded',
        'stepNs': args.step_ns, 'bridgeDelayNs': args.bridge_delay_ns,
        'bridgeDelay': 'Numerical interface delay, not a calibrated device propagation delay'},
        'sources': {name: sha(HERE / name) for name in (
            'firmware_io_cosim.py', 'firmware_io_cosim.v', 'boot_cosim.py', 'boot_cosim.v',
            'circuit.py', 'matrix.py', 'output_circuit.py', 'controller_interface.py', 'serial_observation.py', 'io_scenario.py')}}
    try:
        scenario = load_scenario(args.scenario)
        report['assumptions']['scenario'] = scenario
        report['scenarioSha256'] = sha(args.scenario)
        (out / 'scenario.json').write_text(json.dumps(scenario, indent=2) + '\n')
        (out / 'io_scenario.h').write_text(c_header(scenario))
        report['generatedScenarioHeaderSha256'] = sha(out / 'io_scenario.h')
        if args.rom.stat().st_size != 2048 or sha(args.rom) != ROM_SHA256:
            raise ValueError('Expected standard S600 image')
        report['romSha256'] = sha(args.rom)
        (out / 's600.hex').write_text('\n'.join(f'{b:02x}' for b in args.rom.read_bytes()) + '\n')
        c_sources = [HERE / 'firmware_io_reference.c', ROOT / 'machines/robotron1715m/keyboard.c',
                     ROOT / 'common/cpu/z80.c']
        report['cReferenceSources'] = {str(path): sha(path) for path in [*c_sources,
            ROOT / 'machines/robotron1715m/keyboard.h', ROOT / 'common/cpu/z80.h']}
        subprocess.run(['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-I', str(out),
                        *map(str, c_sources), '-o', str(out / 'reference')], check=True)
        reference = subprocess.check_output([str(out / 'reference'), str(args.rom.resolve())], text=True)
        (out / 'reference.log').write_text(reference)
        reference_events = [(int(cycle), int(bit)) for cycle, bit in re.findall(r'^BIT (\d+) ([01])$', reference, re.M)]
        expected_bits = [bit for _, bit in reference_events]
        if not expected_bits:
            raise ValueError('C reference produced no serial observations')
        report['referenceLogSha256'] = sha(out / 'reference.log')
        report['referenceCoverage'] = observe(scenario, reference_events)
        if not report['referenceCoverage']['passed']:
            raise ValueError('C reference does not exercise the declared scenario observations')
        components, report['connectivitySha256'] = load()
        bridge = json.loads(args.bridge.read_text())
        for lib in bridge['libraries'].values():
            if sha(Path(lib['path'])) != lib['sha256']:
                raise ValueError('Bridge library provenance mismatch')
        report['bridge'] = bridge
        libs = {key: value['path'] for key, value in bridge['libraries'].items()}
        if any('"' in path or '\n' in path for path in libs.values()):
            raise ValueError('Unsupported quote/newline in library path')
        tv80 = ROOT / 'third_party/cpu/tv80'
        report['tv80'] = json.loads((tv80 / 'SOURCE.json').read_text())
        for name, digest in report['tv80']['files'].items():
            if sha(tv80 / name) != digest:
                raise ValueError('TV80 source differs: ' + name)
        subprocess.run(['python3', str(HERE.parent / 'generate.py'), '--check'], check=True)
        (out / 'controller_analog.v').write_text(generate(explicit_cpu_drive=True, resolved_bus=True))
        hdl = [*sorted(tv80.glob('*.v')), HERE.parent / 'chips.v', HERE.parent / 'generated/controller.v',
               HERE / 'boot_cosim.v', HERE / 'firmware_io_cosim.v', out / 'controller_analog.v']
        report['hdlSha256'] = {str(path): sha(path) for path in hdl}
        subprocess.run(['iverilog', '-g2012', '-s', 'firmware_io_cosim', '-o', str(out / 'io.vvp'),
                        *map(str, hdl)], check=True)
        matrix, report['matrixCircuit'] = matrix_circuit(components)
        outputs, info = output_circuit(components)
        report['outputCircuit'] = info
        ground = info['hostGround']
        sense = ' '.join(f'n_SENSE{i}' for i in reversed(range(8)))
        dsense = ' '.join(f'dsense{i}' for i in reversed(range(8)))
        columns = ' '.join(f'dcol{i}' for i in reversed(range(13)))
        sinks = ' '.join(f'sink{i}' for i in reversed(range(13)))
        lines = ['S600 firmware I/O service fixture', f'Vhost {info["hostSupply"]} {ground} PWL(0 0 1u 5)',
                 'Vfixture_clock fixture_clock 0 PULSE(0 5 500n 1n 1n 499n 1u)',
                 'Vfixture_reset fixture_reset 0 ' + reset_source(scenario),
                 *matrix, *outputs,
                 *[f'Vcontact{i} contact{i} 0 ' + contact_source(scenario, i) for i in range(104)],
                 'Esiso_intent siso_intent 0 led0_v 0 1', 'Ecaps_intent caps_intent 0 led1_v 0 1',
                 f'Edata receiver_data 0 {info["serial"]["data"]["cable"]} {ground} 1',
                 f'Eclock receiver_clock 0 {info["serial"]["clock"]["cable"]} {ground} 1',
                 f'Amatrix [{sense}] [{dsense}] data_receiver',
                 'Arxdata [receiver_data] [rx_data] data_receiver',
                 '.model data_receiver adc_bridge(in_low=.8 in_high=2)',
                 'Arxclock [receiver_clock] [rx_clock] clock_receiver',
                 '.model clock_receiver adc_bridge(in_low=1.4 in_high=1.4)',
                 'Afixture [fixture_clock fixture_reset] [fixture_clk fixture_reset_n] clock_receiver',
                 f'Ahdl [fixture_clk fixture_reset_n {dsense} rx_data rx_clock] [dsink csink led1 led0 {columns}] hdl',
                 f'.model hdl d_cosim simulation="{libs["shim"]}" sim_args=["io.vvp"] delay={args.bridge_delay_ns}n',
                 f'+ lib_args=["{libs["libvvp"]}" "{libs["vpi"]}"]',
                 'Adrive [dsink csink led1 led0] [data_intent clock_intent led1_v led0_v] drive',
                 f'Acolumns [{columns}] [{sinks}] drive',
                 '.model drive dac_bridge(out_low=0 out_high=5 out_undef=2.5 t_rise=1n t_fall=1n)',
                 '.save v(receiver_data) v(receiver_clock)', '.control', 'set wr_singlescale', 'set wr_vecnames',
                 f'tran {args.step_ns}n {time_ns(scenario["cycles"])}n', 'wrdata trace.txt v(receiver_data) v(receiver_clock)',
                 'quit', '.endc', '.end']
        (out / 'io.cir').write_text('\n'.join(lines) + '\n')
        report['deckSha256'] = sha(out / 'io.cir')
        report['ngspice'] = subprocess.check_output(['ngspice', '--version'], text=True).strip()
        report['iverilog'] = subprocess.run(['iverilog', '-V'], capture_output=True, text=True, check=True).stdout.splitlines()[0]
        (out / 'run-inputs.json').write_text(json.dumps(report, indent=2) + '\n')
        if args.prepare_only:
            report['preparedOnly'] = True
            print(out / 'io.cir')
            return
        with (out / 'ngspice.log').open('w') as log:
            subprocess.run(['ngspice', '-b', 'io.cir'], cwd=out, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=args.timeout_seconds)
        log = (out / 'ngspice.log').read_text()
        if re.search(r'warning|error|failed|fatal|singular|no vlog_startup_routines', log, re.I):
            raise ValueError('Solver/HDL diagnostics: inspect ngspice.log')
        report['serialTransport'] = validate_transport(log, require_activity=True)
        report['receiverCoverage'] = observe(scenario, report['serialTransport']['received'], electrical=True)
        if not report['receiverCoverage']['passed']:
            raise ValueError('Cable receiver does not satisfy scenario observations')
        received_bits = [bit for _, bit in report['serialTransport']['received']]
        report['cReferenceBits'] = expected_bits
        report['ordinalBitsMatchC'] = received_bits == expected_bits
        if not report['ordinalBitsMatchC']:
            raise ValueError('Electrical receiver bits differ from C emulator under the contact fixture')
        first, last, count = None, None, 0
        with (out / 'trace.txt').open() as stream:
            next(stream)
            for line in stream:
                row = [float(x) for x in line.split()]
                if len(row) != 3 or not all(map(math.isfinite, row)) or (last is not None and row[0] < last):
                    raise ValueError('Invalid receiver waveform')
                first = row[0] if first is None else first
                last = row[0]
                count += 1
        if not count or first > 1e-9 or last + 1e-12 < time_ns(scenario['cycles']) * 1e-9:
            raise ValueError('Incomplete receiver waveform')
        report['waveformRows'] = count
        report['traceSha256'], report['logSha256'] = sha(out / 'trace.txt'), sha(out / 'ngspice.log')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(out / 'report.json')


if __name__ == '__main__':
    main()
