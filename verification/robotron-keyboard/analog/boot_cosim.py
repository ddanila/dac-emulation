#!/usr/bin/env python3
"""Boot TV80/S600 from electrical clock/reset, optionally with live matrix feedback."""
import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from trace_io import open_binary, open_text

from controller_interface import generate
from matrix import LATCH_LOADS, matrix_circuit
from failure_evidence import capture as capture_failure, solver_diagnostic
from ngspice_runtime import identify as identify_runtime, verify as verify_runtime
from output_circuit import output_circuit
from model_coverage import classify
from circuit import elements, load, node, nominal_models
from oscillator_probe import wiring
from reset_probe import RESET_REFS
from serial_observation import validate_transport, SerialMismatch
import board_scenario

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ROM_SHA256 = '4b54891c02a8ec279e2b8aec03489a961fc8647e08ad2036dcf82d0634bf7273'


def sha(path):
    digest = hashlib.sha256()
    with open_binary(path) as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def prepare(args, report):
    out = args.out.resolve()
    components, report['connectivitySha256'] = load()
    if sha(args.rom) != ROM_SHA256 or args.rom.stat().st_size != 2048:
        raise ValueError('Expected standard S600 ROM, not an unidentified specimen image')
    report['romSha256'] = sha(args.rom)
    (out / 's600.hex').write_text('\n'.join(f'{b:02x}' for b in args.rom.read_bytes()) + '\n')
    bridge = json.loads(args.bridge.read_text())
    for lib in bridge['libraries'].values():
        if sha(Path(lib['path'])) != lib['sha256']:
            raise ValueError('Bridge library provenance mismatch')
    report['bridge'] = bridge
    libs = {key: value['path'] for key, value in bridge['libraries'].items()}
    if any('"' in path or '\n' in path for path in libs.values()):
        raise ValueError('Unsupported quote/newline in library path')
    tv80 = ROOT / 'third_party/cpu/tv80'
    source = json.loads((tv80 / 'SOURCE.json').read_text())
    for name, digest in source['files'].items():
        if sha(tv80 / name) != digest:
            raise ValueError('TV80 source differs: ' + name)
    report['tv80'] = source
    subprocess.run([sys.executable, str(HERE.parent / 'generate.py'), '--check'], check=True)
    (out / 'controller_analog.v').write_text(generate(explicit_cpu_drive=True, resolved_bus=True))
    hdl = [*sorted(tv80.glob('*.v')), HERE.parent / 'chips.v',
           HERE.parent / 'generated/controller.v', HERE / 'boot_cosim.v', out / 'controller_analog.v']
    report['hdlSha256'] = {str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path): sha(path) for path in hdl}
    subprocess.run([args.iverilog, '-g2012', '-s', 'boot_cosim',
                    '-Pboot_cosim.ELECTRICAL_MATRIX=' + str(int(args.electrical_matrix)),
                    '-Pboot_cosim.ELECTRICAL_OUTPUTS=' + str(int(args.electrical_outputs)),
                    '-Pboot_cosim.EXPLICIT_CPU_DRIVE=' + str(int(not args.wr_only_data)),
                    '-Pboot_cosim.RESOLVED_BUS=' + str(int(not args.bypass_rom_bus)), '-o', str(out / 'boot.vvp'),
                    *map(str, hdl)], check=True)
    osc, osc_models, unused, clock_source, cpu_clock = wiring(components)
    reset, reset_models = elements(components, RESET_REFS)
    reset_bridge = components['BR2']
    if reset_bridge['type'] != 'BRIDGE' or set(reset_bridge['pins']) != {'1', '2'}:
        raise ValueError('Unexpected BR2 topology')
    reset_source, cpu_reset = [node(reset_bridge['pins'][p]) for p in ('1', '2')]
    if cpu_reset != node(components['A5']['pins']['26']):
        raise ValueError('BR2 no longer feeds CPU reset')
    report['electricalModels'] = {**osc_models, **reset_models, 'BR2': '1 milliohm closed'}
    report['unconnectedA7Pins'] = unused
    report['cpuClockNet'], report['cpuResetNet'] = cpu_clock, cpu_reset
    gate_file = 'ls_nand_dc.cir' if args.gate_profile == 'dl000-dc' else 'ls_nand_nominal.cir'
    (out / gate_file).write_bytes((HERE / gate_file).read_bytes())
    report['gateModel'] = {'file': gate_file, 'sha256': sha(out / gate_file)}
    sense_inputs = ' '.join(f'dsense{i}' for i in reversed(range(8)))
    sense_nodes = ' '.join(f'n_SENSE{i}' for i in reversed(range(8)))
    column_outputs = ' '.join(f'dcol{i}' for i in reversed(range(13)))
    column_nodes = ' '.join(f'sink{i}' for i in reversed(range(13)))
    if args.electrical_matrix:
        matrix_lines, matrix_info = matrix_circuit(components, include_models=False, latch_load=args.latch_load, column_load_pf=args.column_load_pf)
        report['matrixCircuit'] = matrix_info
        report['electricalModels'].update(matrix_info['models'])
        matrix_lines += [f'Vcontact{i} contact{i} 0 ' +
                         (board_scenario.contact_source(args.scenario_data, i) if args.scenario_data else
                          str(5 if i in args.contacts else 0)) for i in range(104)]
    else:
        matrix_lines = [f'Vunusedsense{i} n_SENSE{i} 0 0' for i in range(8)]
    if args.electrical_outputs:
        output_lines, output_info = output_circuit(components)
        report['outputCircuit'] = output_info
        report['outputControlUnknowns'] = 'DAC X maps to 2.5 V; nominal load response is not a physical prediction of unknown logic'
        report['electricalModels'].update(output_info['models'])
        power_lines = [f'Vhost {output_info["hostSupply"]} {output_info["hostGround"]} PWL(0 0 {args.rise_us}u 5)']
        output_lines += ['Esiso_intent siso_intent 0 led0_v 0 1',
                         'Ecaps_intent caps_intent 0 led1_v 0 1']
        serial_trace = [f'v({output_info["serial"][label]["cable"]},{output_info["hostGround"]})'
                        for label in ('data', 'clock')]
        receiver_lines = [
            f'Ereceiver_data receiver_data 0 {output_info["serial"]["data"]["cable"]} {output_info["hostGround"]} 1',
            f'Ereceiver_clock receiver_clock 0 {output_info["serial"]["clock"]["cable"]} {output_info["hostGround"]} 1']
    else:
        output_lines = []
        power_lines = [f'Vcc n_p5V 0 PWL(0 0 {args.rise_us}u 5)']
        serial_trace = ['v(data_intent)', 'v(clock_intent)']
        receiver_lines = ['Vreceiver_data receiver_data 0 0', 'Vreceiver_clock receiver_clock 0 0']
    trace_signals = [f'v({cpu_clock})', f'v({cpu_reset})', *serial_trace]
    report['traceSignals'] = trace_signals
    report['modelCoverage'] = classify(components, report['electricalModels'],
                                       args.electrical_matrix, args.electrical_outputs, not args.bypass_rom_bus)
    lines = ['Coupled electrical oscillator/reset and TV80 S600 boot',
             *power_lines, '.include ' + gate_file,
             f'.options reltol={args.reltol} vntol={args.vntol} abstol={args.abstol}',
             *nominal_models(100, args.npn_profile), *osc, *reset, *matrix_lines, *output_lines, *receiver_lines,
             f'RBR2 {reset_source} {cpu_reset} .001',
             f'Rresetload {cpu_reset} 0 1g', f'Cresetload {cpu_reset} 0 10p',
             f'Ain [{cpu_clock} {cpu_reset}] [dclk drst] receiver',
             '.model receiver adc_bridge(in_low=1.4 in_high=1.4)',
             f'Amatrix [{sense_nodes}] [{sense_inputs}] sense_receiver',
             '.model sense_receiver adc_bridge(in_low=0.8 in_high=2)',
             'Arxdata [receiver_data] [rx_data] sense_receiver',
             'Arxclock [receiver_clock] [rx_clock] receiver',
             f'Ahdl [dclk drst {sense_inputs} rx_data rx_clock] [dsink csink led1 led0 {column_outputs}] hdl',
             f'.model hdl d_cosim simulation="{libs["shim"]}" sim_args=["boot.vvp"] delay={args.bridge_delay_ns}n',
             f'+ lib_args=["{libs["libvvp"]}" "{libs["vpi"]}"]',
             'Adac [dsink csink led1 led0] [data_intent clock_intent led1_v led0_v] observation',
             f'Acolumns [{column_outputs}] [{column_nodes}] observation',
             '.model observation dac_bridge(out_low=0 out_high=5 out_undef=2.5 t_rise=1n t_fall=1n)',
             # Save a tail window to avoid storing the entire power-on delay. Simulation
             # still begins at zero; no capacitor initial conditions or injected clock/reset.
             '.save ' + ' '.join(trace_signals),
             '.control', 'set wr_singlescale', 'set wr_vecnames',
             f'tran {args.step_ns}n {report["assumptions"]["traceWindowSeconds"][1]:.12g} 124m',
             'wrdata trace.txt ' + ' '.join(trace_signals),
             'quit', '.endc', '.end']
    (out / 'boot.cir').write_text('\n'.join(lines) + '\n')
    report['deckSha256'] = sha(out / 'boot.cir')


def validate(out, report):
    log = (out / 'ngspice.log').read_text()
    if solver_diagnostic(log):
        raise ValueError('Solver/bridge diagnostics: inspect ngspice.log')
    resets = [(int(t)*1e-12, value) for t, value in re.findall(r'^RESET (\d+) ([01xz])$', log, re.M)]
    boots = [tuple(line.split()) for line in re.findall(r'^BOOT (.+)$', log, re.M)]
    fetches = re.findall(r'^FIRST_FETCH (\d+) ([0-9a-fx]+) ([0-9a-fx]+)$', log, re.M)
    report['resetEvents'] = resets
    if not resets or resets[-1][1] != '1' or not .12 < resets[-1][0] < .126:
        raise ValueError('Expected electrical reset release absent from HDL')
    release = resets[-1][0]
    if not any(value == '0' and t < .12 for t, value in resets):
        raise ValueError('No initial reset assertion reached HDL')
    after = [(int(t)*1e-12, address, value) for t, address, value in fetches if int(t)*1e-12 >= release]
    if len(after) != 1 or after[0][1] != '0000':
        raise ValueError('CPU did not start instruction fetching at ROM address zero')
    if int(after[0][2], 16) != int((out / 's600.hex').read_text().splitlines()[0], 16):
        raise ValueError('First fetched byte does not match S600')
    settled = [b for b in boots if int(b[0])*1e-12 > release]
    if not settled:
        raise ValueError('CPU made no sustained post-reset progress')
    last = settled[-1]
    report['lastBootSample'] = dict(zip(('timePs', 'cycles', 'fetchSamples', 'ioReadSamples',
                                       'ioWriteSamples', 'addressHex', 'ledBits'), last))
    if int(last[1]) < 1000 or int(last[2]) < 100 or int(last[3]) == 0:
        raise ValueError('Boot did not exercise instruction fetch and keyboard scanning')
    report['idleBootPolicy'] = 'No serial write is required without a key stimulus; transmit scenarios are separate'
    if report['assumptions'].get('serialReceiver'):
        report['serialTransport'] = validate_transport(log, require_activity=bool(report.get('scenario')))
    if report.get('scenario'):
        report['scenarioCoverage'] = board_scenario.coverage(report['scenario'], report['serialTransport']['received'])
        if not report['scenarioCoverage']['passed']:
            raise ValueError('Full-board contact scenario observations are not satisfied')
    if 'x' in last[5] + last[6]:
        raise ValueError('Unknown CPU address or LED state after boot')
    # Stream traces: do not duplicate a long analog run in Python memory.
    count, low_reset, high_reset, clock_low, clock_high = 0, False, False, False, False
    first, last_time = None, None
    with open_text(out / 'trace.txt') as stream:
        next(stream)
        for line in stream:
            row = [float(v) for v in line.split()]
            if len(row) != 5 or not all(map(math.isfinite, row)):
                raise ValueError('Invalid coupled waveform')
            t, clk, rst, data, clock = row
            if last_time is not None and t < last_time:
                raise ValueError('Waveform time reversal')
            first = t if first is None else first
            last_time = t
            count += 1
            low_reset |= rst < .8
            high_reset |= rst > 2
            clock_low |= clk < .8
            clock_high |= clk > 2
    if not all((count, low_reset, high_reset, clock_low, clock_high)) or first > .12401 or last_time < report['assumptions']['traceWindowSeconds'][1] - 1e-12:
        raise ValueError('Coupled analog waveform lacks reset/clock activity or endpoints')
    report['waveformRows'] = count
    report['firstFetchAfterRelease'] = after[0]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom', type=Path, required=True)
    p.add_argument('--bridge', type=Path, default=ROOT / 'build/keyboard-controller-analog/bridge/bridge.json')
    p.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-analog/coupled-boot')
    p.add_argument('--bypass-rom-bus', action='store_true', help='Diagnostic: feed ROM directly to CPU input')
    p.add_argument('--wr-only-data', action='store_true', help='Retain old WR-only data drive as a diagnostic control')
    p.add_argument('--electrical-outputs', action='store_true')
    p.add_argument('--electrical-matrix', action='store_true')
    p.add_argument('--contacts', default='', help='Comma-separated fixture contact indices held closed from power-on')
    p.add_argument('--scenario', type=Path, help='Contact recipe at 125 ms origin, 1 us wall-time ticks; requires electrical matrix and outputs')
    p.add_argument('--prepare-only', action='store_true', help='Generate inputs without claiming a simulation pass')
    p.add_argument('--rise-us', type=float, default=1)
    p.add_argument('--gate-profile', choices=('nominal', 'dl000-dc'), default='nominal')
    p.add_argument('--npn-profile', choices=('generic', 'sc236-dc'), default='generic')
    p.add_argument('--step-ns', type=float, default=2)
    p.add_argument('--bridge-delay-ns', type=float, default=10, help='Numerical interface delay, not a calibrated pin delay')
    p.add_argument('--timeout-seconds', type=float, default=7200)
    p.add_argument('--ngspice', default='ngspice')
    p.add_argument('--ngspice-spinit', type=Path, help='Explicit spinit with absolute code-model paths')
    p.add_argument('--iverilog', default='iverilog')
    p.add_argument('--latch-load', choices=LATCH_LOADS, default='ideal')
    p.add_argument('--column-load-pf', type=float, default=0, help='Assumed fixture capacitance per column to ground; zero omits it')
    p.add_argument('--reltol', type=float, default=.001)
    p.add_argument('--vntol', type=float, default=1e-6)
    p.add_argument('--abstol', type=float, default=1e-12)
    args = p.parse_args()
    if not math.isfinite(args.column_load_pf) or args.column_load_pf < 0:
        p.error('column-load-pf must be finite and nonnegative')
    if any(not math.isfinite(v) or v <= 0 for v in (args.reltol, args.vntol, args.abstol)):
        p.error('Solver tolerances must be positive and finite')
    if not math.isfinite(args.step_ns) or not 0 < args.step_ns <= 10:
        p.error('step-ns must be in (0, 10]')
    if not math.isfinite(args.bridge_delay_ns) or not 0 < args.bridge_delay_ns <= 100:
        p.error('bridge-delay-ns must be in (0, 100]')
    if not math.isfinite(args.rise_us) or not 0 < args.rise_us <= 10000:
        p.error('rise-us must be in (0, 10000]')
    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0:
        p.error('timeout-seconds must be positive and finite')
    try:
        args.contacts = {int(v) for v in args.contacts.split(',') if v.strip()}
    except ValueError:
        p.error('contacts must be comma-separated integers')
    if not args.contacts <= set(range(104)) or (args.contacts and not args.electrical_matrix):
        p.error('contacts require electrical-matrix and indices 0 through 103')
    args.scenario_data = board_scenario.load_board_scenario(args.scenario) if args.scenario else None
    if args.scenario and (args.contacts or not args.electrical_matrix or not args.electrical_outputs):
        p.error('scenario requires electrical-matrix and electrical-outputs, without static contacts')
    if args.column_load_pf and not args.electrical_matrix:
        p.error('column-load-pf requires electrical-matrix')
    if args.latch_load != 'ideal' and not args.electrical_matrix:
        p.error('latch-load stress requires electrical-matrix')
    stop = board_scenario.stop_seconds(args.scenario_data) if args.scenario_data else .127
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    for name in ('report.json', 'trace.txt', 'ngspice.log'):
        (out / name).unlink(missing_ok=True)
    report = {'passed': False, 'scope': __doc__,
              'assumptions': {'receiverThresholdVolts': 1.4,
                              'solver': {'reltol': args.reltol, 'vntol': args.vntol, 'abstol': args.abstol},
                              'receiver': 'Single nominal threshold avoids counting both edges of an X band as clock edges',
                              'analogModels': 'Nominal reset semiconductors and exploratory LS NAND; no specimen timing claim',
                              'latchLoad': args.latch_load, 'columnLoadPf': args.column_load_pf, 'npnProfile': args.npn_profile, 'gateProfile': args.gate_profile,
                              'serialReceiver': args.electrical_outputs,
                              'remainingDigitalBoundaries': ([] if args.electrical_matrix else ['matrix sensing']) + ['CPU/peripheral buses'] + ([] if args.electrical_outputs else ['LED and serial output loading']),
                              'romBus': 'Direct CPU input diagnostic' if args.bypass_rom_bus else 'Resolved CPU/ROM/latch bus from numbered schematic pins',
                              'cpuDataDrive': 'WR-only diagnostic' if args.wr_only_data else 'TV80 write-cycle intent gated by reset and bus ownership',
                              'electricalOutputs': args.electrical_outputs, 'electricalMatrix': args.electrical_matrix, 'closedContacts': sorted(args.contacts),
                              'contacts': 'Static diode-free fixture in electrical mode; boot test, not firmware scenario qualification',
                              'traceWindowSeconds': [.124, stop], 'simulationStartSeconds': 0,
                              'bridgeDelayNs': args.bridge_delay_ns,
                              'bridgeDelay': 'Numerical synchronization only; not calibrated device propagation',
                              'maximumStepNs': args.step_ns, 'timeoutSeconds': args.timeout_seconds, 'supplyRiseUs': args.rise_us,
                              'knownLimit': 'The nominal model failed to produce a reset pulse with a 10 ns supply ramp'},
              'sources': {name: sha(HERE / name) for name in ('boot_cosim.py', 'boot_cosim.v',
                            'circuit.py', 'sc236_dc.cir', 'oscillator_probe.py', 'reset_probe.py',
                            'ls_nand_dc.cir' if args.gate_profile == 'dl000-dc' else 'ls_nand_nominal.cir',
                            'controller_interface.py', 'matrix.py', 'latch_limits.json', 'failure_evidence.py', 'ngspice_runtime.py', 'output_circuit.py', 'model_coverage.py',
                            'serial_observation.py', 'board_scenario.py', 'io_scenario.py', 'trace_io.py')}}
    if args.scenario_data:
        report['scenario'] = args.scenario_data
        report['scenarioSha256'] = sha(args.scenario)
        report['assumptions']['contacts'] = 'Timed diode-free fixture; recipe indices mean 1 us wall-time ticks from 125 ms, not CPU cycles'
        report['assumptions']['scenarioComparison'] = 'Receiver observation windows only; no C ordinal or CPU cycle equivalence claim'
        (out / 'scenario.json').write_text(json.dumps(args.scenario_data, indent=2) + '\n')
    try:
        prepare(args, report)
        report['ngspiceRuntime'], engine_env = identify_runtime(args.ngspice, args.ngspice_spinit)
        engine = report['ngspiceRuntime']['executable']['path']
        report['ngspice'] = subprocess.check_output([engine, '--version'], text=True).strip()
        report['iverilog'] = subprocess.run([args.iverilog, '-V'], capture_output=True, text=True, check=True).stdout.splitlines()[0]
        (out / 'run-inputs.json').write_text(json.dumps(report, indent=2) + '\n')
        if args.prepare_only:
            report['preparedOnly'] = True
            print(out / 'boot.cir')
            return
        with (out / 'ngspice.log').open('w') as log:
            subprocess.run([engine, '-n', '-b', 'boot.cir'], cwd=out, env=engine_env, stdout=log,
                           stderr=subprocess.STDOUT, check=True, timeout=args.timeout_seconds)
        verify_runtime(report['ngspiceRuntime'])
        report['logSha256'] = sha(out / 'ngspice.log')
        report['traceSha256'] = sha(out / 'trace.txt')
        validate(out, report)
        report['passed'] = True
    except Exception as error:
        if isinstance(error, SerialMismatch):
            report['serialFailure'] = error.details
        report['error'] = str(error)
        report['failureArtifacts'] = capture_failure(out, ('ngspice.log', 'trace.txt'))
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(out / 'report.json')


if __name__ == '__main__':
    main()
