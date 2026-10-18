#!/usr/bin/env python3
"""Exercise S600 matrix/cable feedback with CPU-side clock/reset service fixtures."""
import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path
from trace_io import open_text, open_binary
from compressed_output import capture as capture_compressed

from boot_cosim import ROM_SHA256, sha
from circuit import load, node
from controller_interface import generate
from electrical_bus_interface import generate_service
from cpu_read_phase_candidate import CIRCUIT_PROFILES, circuit_sources
from write_control import wiring as wr_wiring
from write_control_observation import measure as measure_wr, WriteMismatch
from bus_driver import wiring as bus_wiring
from bus_observation import measure as measure_bus, BusMismatch
from transient_analysis import with_minimum_breakpoint
from model_coverage import classify_service
from cpu_control import wiring as cpu_wiring
from logic_control import wiring as logic_wiring
from matrix import LATCH_LOADS, matrix_circuit
from failure_evidence import capture as capture_failure, solver_diagnostic
from ngspice_runtime import identify as identify_runtime, verify as verify_runtime
from output_circuit import output_circuit
from ttl7406_output_probe import driver_circuit, checked_dc_reference
from serial_observation import validate_transport, first_reference_difference, SerialMismatch
from io_scenario import load as load_scenario, contact_source, reset_source, c_header, time_ns, observe
from reset_observation import validate_service_reset, ResetMismatch
from led_observation import measure as measure_leds

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom', type=Path, required=True)
    p.add_argument('--scenario', type=Path, default=HERE / 'scenarios/single-press.json')
    p.add_argument('--led-trace', action='store_true', help='Retain and check firmware-driven LED currents')
    p.add_argument('--require-led-activity', action='store_true', help='Require both indicators to exercise settled on and off states')
    p.add_argument('--prepare-only', action='store_true')
    p.add_argument('--compress-traces', action='store_true', help='Stream waveforms through POSIX FIFOs to lossless XZ')
    p.add_argument('--compression-preset', type=int, choices=range(10), default=1, help='Lossless XZ preset; higher values trade compression time and memory for storage')
    p.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-analog/firmware-io')
    p.add_argument('--bridge', type=Path, default=ROOT / 'build/keyboard-controller-analog/bridge/bridge.json')
    p.add_argument('--step-ns', type=float, default=50)
    p.add_argument('--bridge-delay-ns', type=float, default=10)
    p.add_argument('--timeout-seconds', type=float, default=1800)
    p.add_argument('--ngspice', default='ngspice')
    p.add_argument('--ngspice-spinit', type=Path, help='Explicit spinit with absolute code-model paths')
    p.add_argument('--latch-load', choices=LATCH_LOADS, default='ideal')
    p.add_argument('--column-load-pf', type=float, default=0, help='Assumed fixture capacitance per column to ground; zero omits it')
    p.add_argument('--electrical-cpu-pullups', action='store_true')
    p.add_argument('--electrical-bus', action='store_true', help='Experimental linear bus-driver stress fixture with electrical receiver feedback')
    p.add_argument('--rom-read-envelope', action='store_true', help='Conservative Intel 2716 read timing; requires electrical-bus')
    p.add_argument('--cpu-profile', choices=CIRCUIT_PROFILES, default='tv80')
    p.add_argument('--serial-driver', choices=('nominal', '7406-dc'), default='nominal')
    p.add_argument('--bus-latch-pf', type=float, help='Explicit undocumented latch-output capacitance per pin')
    p.add_argument('--bus-7406-pf', type=float, help='Explicit undocumented 7406-input capacitance')
    p.add_argument('--electrical-logic-pullups', action='store_true')
    p.add_argument('--logic-load-pf', type=float, default=0, help='Assumed capacitance per control net; requires electrical logic pullups')
    p.add_argument('--minimum-breakpoint-fs', type=float, help='Explicit ngspice breakpoint spacing via deck tran/run')
    p.add_argument('--electrical-wr', action='store_true', help='Finite CPU WR drive into transistor clock gate; requires electrical-bus and 7406-dc')
    args = p.parse_args()
    if args.rom_read_envelope and not args.electrical_bus:
        p.error('ROM read envelope requires electrical-bus')
    if args.cpu_profile != 'tv80' and not args.electrical_bus:
        p.error('Experimental CPU profile requires electrical-bus observation')
    if args.electrical_wr and (not args.electrical_bus or args.serial_driver != '7406-dc'):
        p.error('electrical-wr requires electrical-bus and serial-driver 7406-dc')
    bus_caps = (args.bus_latch_pf, args.bus_7406_pf)
    if args.electrical_bus:
        if any(value is None or not math.isfinite(value) or value < 0 for value in bus_caps):
            p.error('electrical-bus requires finite nonnegative bus-latch-pf and bus-7406-pf')
    elif any(value is not None for value in bus_caps):
        p.error('Bus capacitance fixtures require electrical-bus')
    if args.minimum_breakpoint_fs is not None and (not math.isfinite(args.minimum_breakpoint_fs) or args.minimum_breakpoint_fs <= 0):
        p.error('minimum-breakpoint-fs must be positive and finite')
    if not math.isfinite(args.logic_load_pf) or args.logic_load_pf < 0 or (args.logic_load_pf and not args.electrical_logic_pullups):
        p.error('logic-load-pf must be finite and nonnegative, and requires electrical-logic-pullups')
    if not math.isfinite(args.column_load_pf) or args.column_load_pf < 0:
        p.error('column-load-pf must be finite and nonnegative')
    if not 0 < args.step_ns <= 100 or not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0:
        p.error('step-ns must be in (0, 100]; timeout-seconds must be positive and finite')
    if not 0 < args.bridge_delay_ns <= 100:
        p.error('bridge-delay-ns must be in (0, 100]')
    if args.require_led_activity:
        args.led_trace = True
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.compress_traces and any(out.glob('*trace.txt*')):
        p.error('Compressed capture requires a fresh waveform output directory')
    for name in ('report.json', 'trace.txt', 'led-trace.txt', 'bus-trace.txt', 'driver-trace.txt', 'wr-trace.txt', 'ngspice.log'):
        (out / name).unlink(missing_ok=True)
    report = {'passed': False, 'scope': __doc__, 'assumptions': {
        'electricalCpuPullups': args.electrical_cpu_pullups,
        'electricalLogicPullups': args.electrical_logic_pullups, 'logicLoadPf': args.logic_load_pf,
        'logicClockReceiver': 'Nominal 1.4 V threshold; not calibrated DL074 switching timing',
        'minimumBreakpointFs': args.minimum_breakpoint_fs,
        'analysisInvocation': 'deck-tran/run' if args.minimum_breakpoint_fs is not None else 'control-tran',
        'clockPeriodNs': 1000, 'resetRampStartNs': 1000000, 'fixtureEdgeNs': 1,
        'fixtureThresholdVolts': 1.4, 'br1Closed': False, 'br2Closed': False,
        'contactTransitionNs': 1, 'latchLoad': args.latch_load, 'columnLoadPf': args.column_load_pf,
        'supply': '1 us host-supply ramp through cable paths; fixture holds CPU reset for 1 ms; no board power-on-reset qualification',
        'semiconductors': 'Generic matrix PNP and nominal output/load models',
        'coverage': 'TV80, resolved ROM/latch bus, electrical matrix and cable receiver; oscillator/reset generators excluded',
        'ledTrace': args.led_trace, 'requireLedActivity': args.require_led_activity,
        'stepNs': args.step_ns, 'bridgeDelayNs': args.bridge_delay_ns,
        'bridgeDelay': 'Numerical interface delay, not a calibrated device propagation delay'},
        'sources': {name: sha(HERE / name) for name in (
            'firmware_io_cosim.py', 'firmware_io_cosim.v', 'boot_cosim.py', 'boot_cosim.v',
            'ngspice_runtime.py', 'circuit.py', 'matrix.py', 'latch_limits.json', 'failure_evidence.py', 'output_circuit.py', 'controller_interface.py', 'logic_control.py', 'model_coverage.py', 'reset_probe.py', 'oscillator_probe.py', 'cpu_control.py', 'cpu_clock_limits.json', 'serial_observation.py',
            'io_scenario.py', 'reset_observation.py', 'led_observation.py', 'trace_io.py', 'compressed_output.py', 'transient_analysis.py')}}
    report['waveformCompression'] = {'format': 'xz', 'preset': args.compression_preset} if args.compress_traces else None
    report['assumptions']['cpuProfile'] = args.cpu_profile
    report['assumptions']['romReadEnvelope'] = bool(getattr(args, 'rom_read_envelope', False))
    if getattr(args, 'rom_read_envelope', False):
        report.setdefault('sources', {})['eprom2716.v'] = sha(HERE / 'eprom2716.v')
        report['assumptions']['romTimingBoundary'] = ('Intel 2716 450 ns-grade read envelope; '
            'unspecified intervals propagate X. No U556 calibration or physical transition prediction; '
            'the bridge unknown-drive voltage is a numerical surrogate, not a qualified pin voltage.')
    report['sources']['cpu_read_phase_candidate.py'] = sha(HERE / 'cpu_read_phase_candidate.py')
    if args.serial_driver != 'nominal':
        report['assumptions']['serialDriver'] = args.serial_driver
        report['sources'].update({name: sha(HERE / name) for name in ('ttl7406_output_probe.py', 'ttl7406_nominal.cir', 'ttl7406_limits.json')})
    if args.electrical_bus:
        report['assumptions'].update(electricalBus=True, busLatchPf=args.bus_latch_pf,
                                     bus7406Pf=args.bus_7406_pf,
                                     waveformNumdgt=17,
                                     busDriver='Linear 5 V DC-endpoint stress fixture; no calibrated I/V or leakage')
        report['sources'].update({name: sha(HERE / name) for name in (
            'electrical_bus_interface.py', 'bus_driver.py', 'bus_load.py', 'bus_inventory.py', 'bus_limits.json', 'bus_observation.py')})
    if args.electrical_wr:
        report['assumptions']['electricalWr'] = True
        report['sources'].update({name: sha(HERE / name) for name in ('write_control.py', 'write_control_observation.py')})
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
        (out / 'controller_analog.v').write_text(generate_service(electrical_wr=args.electrical_wr, cpu_profile=args.cpu_profile, rom_timing=args.rom_read_envelope) if args.electrical_bus else
                                               generate(explicit_cpu_drive=True, resolved_bus=True))
        cpu_sources, report['cpuModel'] = circuit_sources(tv80, out, args.cpu_profile)
        hdl = [*cpu_sources, HERE.parent / 'chips.v', HERE.parent / 'generated/controller.v',
               HERE / 'boot_cosim.v', HERE / 'firmware_io_cosim.v', out / 'controller_analog.v']
        report['hdlSha256'] = {str(path): sha(path) for path in hdl}
        top = 'firmware_io_electrical_bus' if args.electrical_bus else 'firmware_io_cosim'
        subprocess.run(['iverilog', '-g2012', '-s', top, '-o', str(out / 'io.vvp'),
                        f'-P{top}.ELECTRICAL_CPU_PULLUPS=' + str(int(args.electrical_cpu_pullups)),
                        f'-P{top}.ELECTRICAL_LOGIC_PULLUPS=' + str(int(args.electrical_logic_pullups)),
                        *map(str, hdl)], check=True)
        matrix, report['matrixCircuit'] = matrix_circuit(components, latch_load=args.latch_load, column_load_pf=args.column_load_pf)
        if args.serial_driver == '7406-dc':
            report['serialDriverDcReferenceSha256'] = checked_dc_reference()
            outputs, info = driver_circuit(components, args.serial_driver, 1000,
                                           electrical_data_input=args.electrical_bus, electrical_clock_input=args.electrical_wr)
        else:
            outputs, info = output_circuit(components)
        report['outputCircuit'] = info
        logic_lines, logic_inputs = [], 'fixture_reset_n fixture_reset_n fixture_reset_n'
        if args.electrical_logic_pullups:
            logic_lines, logic_models, logic_info = logic_wiring(components, args.logic_load_pf)
            report['logicControlCircuit'] = logic_info
            report['logicControlModels'] = logic_models
            nets = logic_info['nets']
            logic_lines += [
                f'Alogic_levels [{nets["latchEnable"]} {nets["flipFlopRelease"]}] [dlogic_oe dlogic_ff] data_receiver',
                f'Alogic_clock [{nets["ioActive"]}] [dlogic_io] clock_receiver',
                'Alogic_drive [dlogic_sink0 dlogic_sink1] [control_latchEnable_sink control_ioActive_sink] drive']
            logic_inputs = 'dlogic_io dlogic_ff dlogic_oe'
        cpu_lines, cpu_inputs = [], 'fixture_reset_n fixture_reset_n'
        if args.electrical_cpu_pullups:
            cpu_lines, cpu_models, cpu_info = cpu_wiring(components)
            report['cpuControlCircuit'] = cpu_info
            report['cpuControlModels'] = cpu_models
            cpu_lines += [f'Acontrol [{cpu_info["interruptNmiWait"]} {cpu_info["busRequest"]}] [dcontrol dbusrq] data_receiver']
            cpu_inputs = 'dcontrol dbusrq'
        service_models = {**report['matrixCircuit']['models'], **info['models'],
                          **report.get('logicControlModels', {}), **report.get('cpuControlModels', {})}
        report['modelCoverage'] = classify_service(components, service_models,
            args.electrical_cpu_pullups, args.electrical_logic_pullups)
        if args.rom_read_envelope:
            report['modelCoverage']['components']['A8']['model'] += '; conservative Intel 2716 read envelope; unspecified intervals propagate X'
        if args.serial_driver == '7406-dc':
            report['modelCoverage']['components']['A1']['model'] = ('Data and clock gates use published transistor topology with '
                'generic semiconductor parameters and ideal input intent; other gates remain HDL.')
        bus_lines, bus_inputs, bus_outputs = [], '', ''
        if args.electrical_bus:
            limits = json.loads((HERE / 'bus_limits.json').read_text())
            bus_lines, report['busCircuit'] = bus_wiring(components, limits,
                {'I8282': args.bus_latch_pf, '7406': args.bus_7406_pf})
            def vector(prefix, count):
                return ' '.join(f'{prefix}{i}' for i in reversed(range(count)))
            bus_inputs = vector('dbus', 8)
            bus_outputs = vector('dbus_low', 24) + ' ' + vector('dbus_high', 24)
            bus_lines += [f'Abus [{vector("n_D", 8)}] [{bus_inputs}] data_receiver',
                          f'Abus_low [{vector("dbus_low", 24)}] [{vector("bus_low_", 24)}] drive',
                          f'Abus_high [{vector("dbus_high", 24)}] [{vector("bus_high_", 24)}] drive',
                          *[f'Rbus_numerical{i} n_D{i} 0 1e12' for i in range(8)]]
            report['busCircuit']['numericalShuntsOhms'] = 1e12
            for ref in ('A5', 'A8', 'A4'):
                report['modelCoverage']['components'][ref]['model'] += '; data pins use linear electrical stress drivers and pin-capacitance fixtures'
            report['modelCoverage']['components']['A5']['model'] = report['modelCoverage']['components']['A5']['model'].replace('resolved digital data bus', 'electrical data-bus receiver feedback')
            report['modelCoverage']['components']['A1']['model'] += '; D0 uses electrical bus receiver and fixture input capacitance; input bias omitted'
            if args.serial_driver == '7406-dc':
                report['busCircuit']['externalInputLoad'] = info['serialDriver']['dataInput']
                report['busCircuit']['boundary'] = report['busCircuit']['boundary'].replace(
                    'No leakage, 7406 input bias, IC power model', 'No driver leakage or whole-IC power model')
                report['modelCoverage']['components']['A1']['model'] = ('Data gate uses bus-driven transistor topology; '
                    'clock gate uses transistor topology with ideal input intent; other gates remain HDL. '
                    'Generic semiconductor parameters, uncalibrated capacitance and switching timing.')
        if args.electrical_wr:
            wr_lines, report['wrCircuit'] = wr_wiring(components, limits, args.bus_7406_pf)
            bus_lines += wr_lines + ['Awr_drive [dwr_low dwr_high] [wr_low wr_high] drive']
            bus_outputs += ' dwr_low dwr_high'
            report['wrCircuit']['ownershipSource'] = {
                **limits['sources']['u880d'], 'page': 'Printed pages 9-10; PDF pages 10-11',
                'scope': 'Inactive WR during reset; high impedance while BUSACK active. TV80 event timing unqualified.'}
            report['modelCoverage']['components']['A1']['model'] = (
                'Data and clock gates use electrical D0/WR voltages and transistor topology; other gates remain HDL. '
                'Generic semiconductor parameters, uncalibrated capacitance and switching timing.')
            report['modelCoverage']['components']['A5']['model'] += '; WR uses explicit reset/BUSACK ownership and linear DC-endpoint driver'
        ground = info['hostGround']
        sense = ' '.join(f'n_SENSE{i}' for i in reversed(range(8)))
        dsense = ' '.join(f'dsense{i}' for i in reversed(range(8)))
        columns = ' '.join(f'dcol{i}' for i in reversed(range(13)))
        sinks = ' '.join(f'sink{i}' for i in reversed(range(13)))
        lines = ['S600 firmware I/O service fixture', f'Vhost {info["hostSupply"]} {ground} PWL(0 0 1u 5)',
                 'Vfixture_clock fixture_clock 0 PULSE(0 5 500n 1n 1n 499n 1u)',
                 'Vfixture_reset fixture_reset 0 ' + reset_source(scenario),
                 *matrix, *outputs, *logic_lines, *cpu_lines, *bus_lines,
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
                 f'Ahdl [fixture_clk fixture_reset_n {dsense} rx_data rx_clock {logic_inputs} {cpu_inputs}' +
                 (f' {bus_inputs}' if args.electrical_bus else '') + '] [' +
                 (f'{bus_outputs} ' if args.electrical_bus else '') + f'dlogic_sink1 dlogic_sink0 dsink csink led1 led0 {columns}] hdl',
                 f'.model hdl d_cosim simulation="{libs["shim"]}" sim_args=["io.vvp"] delay={args.bridge_delay_ns}n',
                 f'+ lib_args=["{libs["libvvp"]}" "{libs["vpi"]}"]',
                 'Adrive [dsink csink led1 led0] [data_intent clock_intent led1_v led0_v] drive',
                 f'Acolumns [{columns}] [{sinks}] drive',
                 '.model drive dac_bridge(out_low=0 out_high=5 out_undef=2.5 t_rise=1n t_fall=1n)',
                 '.save v(receiver_data) v(receiver_clock)', '.control', 'set wr_singlescale', 'set wr_vecnames',
                 f'tran {args.step_ns}n {time_ns(scenario["cycles"])}n', 'wrdata trace.txt v(receiver_data) v(receiver_clock)',
                 'quit', '.endc', '.end']
        if args.led_trace:
            signals = 'v(siso_intent) v(caps_intent) @dsiso_led[id] @dcaps_led[id]'
            lines.insert(lines.index('.control'), '.save ' + signals)
            lines.insert(lines.index('quit'), 'wrdata led-trace.txt ' + signals)
        if args.electrical_bus:
            signals = ' '.join(f'v(n_D{i})' for i in range(8)) + ' v(n_p5V)'
            lines.insert(lines.index('.control'), '.save ' + signals)
            lines.insert(lines.index('.control') + 1, 'set numdgt=17')
            lines.insert(lines.index('quit'), 'wrdata bus-trace.txt ' + signals)
        if args.serial_driver == '7406-dc':
            lines.insert(lines.index('.control'), '.save i(Vdriver_supply)')
            lines.insert(lines.index('quit'), 'wrdata driver-trace.txt i(Vdriver_supply)')
        if args.electrical_wr:
            signals = f'v({node(report["wrCircuit"]["net"])}) v(wr_low) v(wr_high) @bwr_low[i] @bwr_high[i] v(n_p5V)'
            lines.insert(lines.index('.control'), '.save ' + signals)
            lines.insert(lines.index('quit'), 'wrdata wr-trace.txt ' + signals)
        (out / 'io.cir').write_text(with_minimum_breakpoint('\n'.join(lines) + '\n', args.minimum_breakpoint_fs))
        report['deckSha256'] = sha(out / 'io.cir')
        report['ngspiceRuntime'], engine_env = identify_runtime(args.ngspice, args.ngspice_spinit)
        engine = report['ngspiceRuntime']['executable']['path']
        report['ngspice'] = subprocess.check_output([engine, '--version'], text=True).strip()
        report['iverilog'] = subprocess.run(['iverilog', '-V'], capture_output=True, text=True, check=True).stdout.splitlines()[0]
        (out / 'run-inputs.json').write_text(json.dumps(report, indent=2) + '\n')
        if args.prepare_only:
            report['preparedOnly'] = True
            print(out / 'io.cir')
            return
        trace_names = ['trace.txt'] + (['led-trace.txt'] if args.led_trace else []) + (['bus-trace.txt'] if args.electrical_bus else [])
        if args.serial_driver == '7406-dc':
            trace_names.append('driver-trace.txt')
        if args.electrical_wr:
            trace_names.append('wr-trace.txt')
        with capture_compressed(out, trace_names, args.compress_traces, preset=args.compression_preset) as compressed:
            with (out / 'ngspice.log').open('w') as log:
                subprocess.run([engine, '-n', '-b', 'io.cir'], cwd=out, env=engine_env, stdout=log, stderr=subprocess.STDOUT,
                               check=True, timeout=args.timeout_seconds)
        if args.compress_traces:
            report['compressedWaveforms'] = compressed
        if args.serial_driver == '7406-dc':
            report['driverTraceSha256'] = sha(out / 'driver-trace.txt')
        if args.electrical_wr:
            report['wrTraceSha256'] = sha(out / 'wr-trace.txt')
        if args.electrical_bus:
            digest = hashlib.sha256()
            with open_binary(out / 'bus-trace.txt') as stream:
                for data in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(data)
            report['busTraceSha256'] = digest.hexdigest()
            report['busQualification'] = 'Sampled-voltage and TV80-register checks do not qualify U880 pin timing or calibrated electrical behavior'
        verify_runtime(report['ngspiceRuntime'])
        log = (out / 'ngspice.log').read_text()
        if solver_diagnostic(log):
            raise ValueError('Solver/HDL diagnostics: inspect ngspice.log')
        if args.electrical_bus:
            report['busObservation'] = measure_bus(log, out / 'bus-trace.txt', args.step_ns, args.rom.read_bytes(),
                                                  trace_extent=(0, time_ns(scenario['cycles']) * 1e-9))
        if args.electrical_wr:
            report['wrObservation'] = measure_wr(log, out / 'wr-trace.txt', args.step_ns, time_ns(scenario['cycles']) * 1e-9)
        report['resetDelivery'] = validate_service_reset(log, scenario, args.rom.read_bytes()[0])
        report['serialTransport'] = validate_transport(log, require_activity=True)
        received_bits = [bit for _, bit in report['serialTransport']['received']]
        report['cReferenceBits'] = expected_bits
        report['ordinalBitsMatchC'] = received_bits == expected_bits
        if not report['ordinalBitsMatchC']:
            report['firstSerialDifference'] = first_reference_difference(reference_events, report['serialTransport']['received'])
            raise ValueError('Electrical receiver bits differ from C emulator under the contact fixture')
        report['receiverCoverage'] = observe(scenario, report['serialTransport']['received'], electrical=True)
        if not report['receiverCoverage']['passed']:
            report['firstFailedObservation'] = next(window for window in report['receiverCoverage']['windows'] if not window['passed'])
            raise ValueError('Cable receiver does not satisfy scenario observations')
        first, last, count = None, None, 0
        with open_text(out / 'trace.txt') as stream:
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
        if args.led_trace:
            report['ledTraceSha256'] = sha(out / 'led-trace.txt')
            report['ledObservation'] = measure_leds(out / 'led-trace.txt', args.step_ns, args.require_led_activity, start_seconds=.001)
            if not report['ledObservation']['passed']:
                raise ValueError('Firmware-driven LED load observations failed')
            if report['ledObservation']['firstSampleSeconds'] > 1e-9 or report['ledObservation']['lastSampleSeconds'] + 1e-12 < time_ns(scenario['cycles']) * 1e-9:
                raise ValueError('Incomplete LED waveform')
        report['waveformRows'] = count
        report['traceSha256'], report['logSha256'] = sha(out / 'trace.txt'), sha(out / 'ngspice.log')
        for name, captured in compressed.items():
            if sha(out / name) != captured['sha256']:
                raise ValueError('Compressed waveform differs from producer bytes: ' + name)
        report['passed'] = True
    except Exception as error:
        if isinstance(error, WriteMismatch):
            report['wrFailure'] = error.details
        if isinstance(error, BusMismatch):
            report['busFailure'] = error.details
        if isinstance(error, SerialMismatch):
            report['serialFailure'] = error.details
        if isinstance(error, ResetMismatch):
            report['resetFailure'] = error.details
        report['error'] = str(error)
        names = ['ngspice.log', 'trace.txt', 'led-trace.txt']
        if args.electrical_bus:
            names.append('bus-trace.txt')
        if args.serial_driver == '7406-dc':
            names.append('driver-trace.txt')
        if args.electrical_wr:
            names.append('wr-trace.txt')
        if args.compress_traces:
            names += [name + suffix for name in list(names) if name.endswith('trace.txt') for suffix in ('.xz', '.xz.partial')]
        report['failureArtifacts'] = capture_failure(out, names)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(out / 'report.json')


if __name__ == '__main__':
    main()
