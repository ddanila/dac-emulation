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

from electrical_bus_interface import generate_service
from cpu_read_phase_candidate import CIRCUIT_PROFILES, circuit_sources
from bus_driver import wiring as bus_wiring
from write_control import wiring as wr_wiring
from write_control_observation import measure as measure_wr, WriteMismatch
from bus_observation import measure as measure_bus, BusMismatch
from controller_interface import generate
from matrix import LATCH_LOADS, matrix_circuit
from failure_evidence import capture as capture_failure, solver_diagnostic
from ngspice_runtime import identify as identify_runtime, verify as verify_runtime
from output_circuit import output_circuit
from ttl7406_output_probe import driver_circuit, checked_dc_reference
from transient_analysis import with_minimum_breakpoint
from compressed_output import capture as capture_compressed
from model_coverage import classify
from circuit import elements, load, node, nominal_models
from oscillator_probe import wiring
from gate_models import GATE_MODELS
from clock_voltage import inspect as inspect_clock_voltage
from clock_timing import inspect as inspect_clock_timing
from cpu_control import wiring as control_wiring, reset_load, RESET_LOADS
from logic_control import wiring as logic_wiring
from reset_probe import RESET_REFS
from serial_observation import validate_transport, SerialMismatch
import board_scenario
import supply_stimulus

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ROM_SHA256 = '4b54891c02a8ec279e2b8aec03489a961fc8647e08ad2036dcf82d0634bf7273'


def sha(path):
    digest = hashlib.sha256()
    with open_binary(path) as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def electrical_bus_options(args):
    enabled = getattr(args, 'electrical_bus', False)
    if getattr(args, 'cpu_profile', 'tv80') != 'tv80' and not enabled:
        raise ValueError('Experimental CPU profile requires electrical-bus observation')
    if getattr(args, 'latch_timing_envelope', False) and not enabled:
        raise ValueError('Latch timing envelope requires electrical-bus')
    if getattr(args, 'rom_read_envelope', False) and not enabled:
        raise ValueError('ROM read envelope requires electrical-bus')
    caps = [getattr(args, name, None) for name in ('bus_latch_pf', 'bus_7406_pf')]
    if enabled:
        if not args.electrical_matrix or args.bypass_rom_bus or args.wr_only_data:
            raise ValueError('Electrical bus requires electrical matrix, resolved ROM and explicit CPU drive')
        if any(value is None or not math.isfinite(value) or value < 0 for value in caps):
            raise ValueError('Electrical bus requires explicit finite nonnegative latch and 7406 capacitances')
    elif any(value is not None for value in caps):
        raise ValueError('Bus capacitance fixtures require electrical-bus')
    if getattr(args, 'electrical_wr', False) and (not enabled or not args.electrical_outputs or args.serial_driver != '7406-dc'):
        raise ValueError('Electrical WR requires electrical bus and transistor serial outputs')
    return enabled


def prepare(args, report):
    electrical_bus = electrical_bus_options(args)
    electrical_wr = getattr(args, 'electrical_wr', False)
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
    cpu_profile = getattr(args, 'cpu_profile', 'tv80')
    report.setdefault('assumptions', {})['cpuProfile'] = cpu_profile
    report['assumptions']['latchTimingEnvelope'] = bool(getattr(args, 'latch_timing_envelope', False))
    if getattr(args, 'latch_timing_envelope', False):
        report.setdefault('sources', {})['i8282_timing.v'] = sha(HERE / 'i8282_timing.v')
        report['assumptions']['latchTimingBoundary'] = ('Intel I8282 reference output envelope and storage constraints; '
            'X intervals and bridge unknown-drive voltages are not physical metastability or transition predictions.')
    report['assumptions']['romReadEnvelope'] = bool(getattr(args, 'rom_read_envelope', False))
    if getattr(args, 'rom_read_envelope', False):
        report.setdefault('sources', {})['eprom2716.v'] = sha(HERE / 'eprom2716.v')
        report['assumptions']['romTimingBoundary'] = ('Intel 2716 450 ns-grade read envelope; '
            'unspecified intervals propagate X. No U556 calibration or physical transition prediction; '
            'the bridge unknown-drive voltage is a numerical surrogate, not a qualified pin voltage.')
    report.setdefault('sources', {})['cpu_read_phase_candidate.py'] = sha(HERE / 'cpu_read_phase_candidate.py')
    subprocess.run([sys.executable, str(HERE.parent / 'generate.py'), '--check'], check=True)
    (out / 'controller_analog.v').write_text(generate_service(electrical_wr=electrical_wr, cpu_profile=cpu_profile, rom_timing=getattr(args, 'rom_read_envelope', False), latch_timing=getattr(args, 'latch_timing_envelope', False)) if electrical_bus else
                                           generate(explicit_cpu_drive=True, resolved_bus=True))
    cpu_sources, report['cpuModel'] = circuit_sources(tv80, out, cpu_profile)
    hdl = [*cpu_sources, HERE.parent / 'chips.v',
           HERE.parent / 'generated/controller.v', HERE / 'boot_cosim.v', out / 'controller_analog.v']
    report['hdlSha256'] = {str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path): sha(path) for path in hdl}
    top = 'boot_electrical_bus' if electrical_bus else 'boot_cosim'
    subprocess.run([args.iverilog, '-g2012', '-s', top,
                    f'-P{top}.ELECTRICAL_MATRIX=' + str(int(args.electrical_matrix)),
                    f'-P{top}.ELECTRICAL_OUTPUTS=' + str(int(args.electrical_outputs)),
                    f'-P{top}.ELECTRICAL_CPU_PULLUPS=' + str(int(getattr(args, 'electrical_cpu_pullups', False))),
                    f'-P{top}.ELECTRICAL_LOGIC_PULLUPS=' + str(int(getattr(args, 'electrical_logic_pullups', False))),
                    f'-P{top}.EXPLICIT_CPU_DRIVE=' + str(int(not args.wr_only_data)),
                    f'-P{top}.RESOLVED_BUS=' + str(int(not args.bypass_rom_bus)), '-o', str(out / 'boot.vvp'),
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
    reset_load_lines, report['cpuResetLoad'] = reset_load(components, getattr(args, 'reset_load', 'illustrative'))
    report['assumptions']['resetLoad'] = report['cpuResetLoad']['profile']
    gate_file = GATE_MODELS[args.gate_profile]
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
    supply_data = getattr(args, 'supply_data', None)
    supply_source = supply_stimulus.source(supply_data, args.rise_us)
    if supply_data is not None:
        report['supplyStimulus'] = supply_data
        report['assumptions']['customSupplyStimulus'] = True
        report['assumptions']['supplyRiseUs'] = None
        report.setdefault('sources', {})['supply_stimulus.py'] = sha(HERE / 'supply_stimulus.py')
        (out / 'supply-stimulus.json').write_text(json.dumps(supply_data, indent=2) + '\n')
        report['supplyStimulusSha256'] = sha(out / 'supply-stimulus.json')
    if args.electrical_outputs:
        if args.serial_driver == '7406-dc':
            report['serialDriverDCReferenceSha256'] = checked_dc_reference()
            output_lines, output_info = driver_circuit(components, args.serial_driver, 1000, electrical_data_input=electrical_bus, electrical_clock_input=electrical_wr)
        else:
            output_lines, output_info = output_circuit(components)
        report['outputCircuit'] = output_info
        report['outputControlUnknowns'] = (
            f'DAC X maps uniformly to {args.output_unknown_volts:g} V; diagnostic assumption, '
            'not a measured power-on state or exhaustive mixed-state coverage')
        report['electricalModels'].update(output_info['models'])
        power_lines = [f'Vhost {output_info["hostSupply"]} {output_info["hostGround"]} {supply_source}']
        output_lines += ['Esiso_intent siso_intent 0 led0_v 0 1',
                         'Ecaps_intent caps_intent 0 led1_v 0 1']
        serial_trace = [f'v({output_info["serial"][label]["cable"]},{output_info["hostGround"]})'
                        for label in ('data', 'clock')]
        receiver_lines = [
            f'Ereceiver_data receiver_data 0 {output_info["serial"]["data"]["cable"]} {output_info["hostGround"]} 1',
            f'Ereceiver_clock receiver_clock 0 {output_info["serial"]["clock"]["cable"]} {output_info["hostGround"]} 1']
    else:
        output_lines = []
        power_lines = [f'Vcc n_p5V 0 {supply_source}']
        serial_trace = ['v(data_intent)', 'v(clock_intent)']
        receiver_lines = ['Vreceiver_data receiver_data 0 0', 'Vreceiver_clock receiver_clock 0 0']
    trace_signals = [f'v({cpu_clock})', f'v({cpu_reset})', *serial_trace]
    report['traceSignals'] = trace_signals
    control_lines, control_inputs = [], 'drst drst'
    if getattr(args, 'electrical_cpu_pullups', False):
        control_lines, control_models, control_info = control_wiring(components)
        report['electricalModels'].update(control_models)
        report['cpuControlCircuit'] = control_info
        control_lines += [f'Acontrol [{control_info["interruptNmiWait"]} {control_info["busRequest"]}] [dcontrol dbusrq] sense_receiver']
        control_inputs = 'dcontrol dbusrq'
    logic_inputs = 'drst drst drst'
    if getattr(args, 'electrical_logic_pullups', False):
        logic_lines, logic_models, logic_info = logic_wiring(components, getattr(args, 'logic_load_pf', 0))
        report['electricalModels'].update(logic_models)
        report['logicControlCircuit'] = logic_info
        nets = logic_info['nets']
        control_lines += [*logic_lines,
            f'Alogic_levels [{nets["latchEnable"]} {nets["flipFlopRelease"]}] [dlogic_oe dlogic_ff] sense_receiver',
            f'Alogic_clock [{nets["ioActive"]}] [dlogic_io] receiver',
            'Alogic_drive [dlogic_sink0 dlogic_sink1] [control_latchEnable_sink control_ioActive_sink] observation']
        logic_inputs = 'dlogic_io dlogic_ff dlogic_oe'
    supply_signal = f'v({node(components["A5"]["pins"]["11"])})'
    report['supplyTraceSignal'] = supply_signal
    report['modelCoverage'] = classify(components, report['electricalModels'],
                                       args.electrical_matrix, args.electrical_outputs, not args.bypass_rom_bus)
    if getattr(args, 'rom_read_envelope', False):
        report['modelCoverage']['components']['A8']['model'] += '; conservative Intel 2716 read envelope; unspecified intervals propagate X'
    if getattr(args, 'electrical_cpu_pullups', False):
        report['modelCoverage']['components']['A5']['model'] = (
            'TV80 CPU; electrical interrupt/NMI/wait and bus-request pullups with reference-maximum capacitance; '
            'digital buses, nominal clock/reset input loads; no brownout or input leakage model')
    if args.serial_driver == '7406-dc':
        report['modelCoverage']['components']['A1']['model'] = (
            '7406 HDL logic; data/clock gates use the published-topology DC candidate; '
            'ideal DAC input drive, other gates remain digital; no package or switching qualification')
    if getattr(args, 'electrical_logic_pullups', False):
        for ref, description in {
            'A2.2': 'DL003 HDL gates; latch-enable and I/O-active outputs use nominal electrical sinks; column outputs use the matrix boundary',
            'A4': '8282 HDL latch/bus with electrical output-enable and strobe receivers; input leakage and pin timing unqualified',
            'A6': 'DL074 HDL flip-flops with electrical async-control and clock receivers; no supply-current or propagation calibration',
        }.items():
            report['modelCoverage']['components'][ref]['model'] = description
    if getattr(args, 'latch_timing_envelope', False):
        report['modelCoverage']['components']['A4']['model'] += '; conservative Intel 8282 timing envelope'
    bus_lines, bus_inputs, bus_outputs = [], '', ''
    if electrical_bus:
        limits = json.loads((HERE / 'bus_limits.json').read_text())
        bus_lines, report['busCircuit'] = bus_wiring(components, limits,
            {'I8282': args.bus_latch_pf, '7406': args.bus_7406_pf})
        def vector(prefix, count):
            return ' '.join(f'{prefix}{i}' for i in reversed(range(count)))
        bus_inputs = ' ' + vector('dbus', 8)
        bus_outputs = vector('dbus_low', 24) + ' ' + vector('dbus_high', 24) + ' '
        bus_lines += [f'Abus [{vector("n_D", 8)}] [{vector("dbus", 8)}] sense_receiver',
                      f'Abus_low [{vector("dbus_low", 24)}] [{vector("bus_low_", 24)}] observation',
                      f'Abus_high [{vector("dbus_high", 24)}] [{vector("bus_high_", 24)}] observation',
                      *[f'Rbus_numerical{i} n_D{i} 0 1e12' for i in range(8)]]
        report['busCircuit']['numericalShuntsOhms'] = 1e12
        report['assumptions'].update(electricalBus=True, busLatchPf=args.bus_latch_pf,
            bus7406Pf=args.bus_7406_pf, waveformNumdgt=17,
            busBoundary='Electrical data pins only; address/control outputs remain digital. Clock and reset come from the board circuit.')
        report['assumptions']['romBus'] = 'Electrical CPU/ROM/latch data-bus receiver feedback'
        if 'remainingDigitalBoundaries' in report['assumptions']:
            report['assumptions']['remainingDigitalBoundaries'] = [
                'CPU/peripheral address and control buses' if item == 'CPU/peripheral buses' else item
                for item in report['assumptions']['remainingDigitalBoundaries']]
        report.setdefault('sources', {}).update({name: sha(HERE / name) for name in (
            'electrical_bus_interface.py', 'firmware_io_cosim.v', 'bus_driver.py', 'bus_load.py',
            'bus_inventory.py', 'bus_limits.json', 'bus_observation.py')})
        for ref in ('A5', 'A8', 'A4'):
            report['modelCoverage']['components'][ref]['model'] = report['modelCoverage']['components'][ref]['model'].replace(
                'digital buses', 'digital address/control buses') + '; data pins use electrical endpoint drivers and capacitance fixtures'
        if args.serial_driver == '7406-dc':
            report['busCircuit']['externalInputLoad'] = output_info['serialDriver']['dataInput']
            report['busCircuit']['boundary'] = report['busCircuit']['boundary'].replace(
                'No leakage, 7406 input bias, IC power model', 'No driver leakage or whole-IC power model')
            report['modelCoverage']['components']['A1']['model'] = (
                'Data gate uses electrical D0 input and transistor topology; clock gate input is ideal HDL intent; '
                'other gates remain digital. Generic device parameters; switching timing unqualified.')
    if electrical_wr:
        wr_lines, report['wrCircuit'] = wr_wiring(components, limits, args.bus_7406_pf)
        bus_lines += wr_lines + ['Awr_drive [dwr_low dwr_high] [wr_low wr_high] observation']
        bus_outputs += 'dwr_low dwr_high '
        report['assumptions']['electricalWr'] = True
        report['wrCircuit']['ownershipSource'] = {
            **limits['sources']['u880d'], 'page': 'Printed pages 9-10; PDF pages 10-11',
            'scope': 'Inactive WR during reset; release during BUSACK. TV80 event timing unqualified.'}
        report['sources'].update({name: sha(HERE / name) for name in ('write_control.py', 'write_control_observation.py')})
        report['modelCoverage']['components']['A1']['model'] = (
            'Electrical D0 and WR voltages drive transistor data/clock gates; other gates remain digital. '
            'Generic device parameters; switching timing unqualified.')
        report['modelCoverage']['components']['A5']['model'] += '; electrical WR output with reset/BUSACK ownership'
    lines = ['Coupled electrical oscillator/reset and TV80 S600 boot',
             *power_lines, '.include ' + gate_file,
             f'.options reltol={args.reltol} vntol={args.vntol} abstol={args.abstol}',
             *nominal_models(100, args.npn_profile), *osc, *reset, *matrix_lines, *output_lines, *receiver_lines, *control_lines, *bus_lines,
             f'RBR2 {reset_source} {cpu_reset} .001',
             *reset_load_lines,
             f'Ain [{cpu_clock} {cpu_reset}] [dclk drst] receiver',
             '.model receiver adc_bridge(in_low=1.4 in_high=1.4)',
             f'Amatrix [{sense_nodes}] [{sense_inputs}] sense_receiver',
             '.model sense_receiver adc_bridge(in_low=0.8 in_high=2)',
             'Arxdata [receiver_data] [rx_data] sense_receiver',
             'Arxclock [receiver_clock] [rx_clock] receiver',
             f'Ahdl [dclk drst {sense_inputs} rx_data rx_clock {control_inputs} {logic_inputs}{bus_inputs}] [{bus_outputs}dsink csink led1 led0 {column_outputs} dlogic_sink1 dlogic_sink0] hdl',
             f'.model hdl d_cosim simulation="{libs["shim"]}" sim_args=["boot.vvp"] delay={args.bridge_delay_ns}n',
             f'+ lib_args=["{libs["libvvp"]}" "{libs["vpi"]}"]',
             'Adac [dsink csink led1 led0] [data_intent clock_intent led1_v led0_v] observation',
             f'Acolumns [{column_outputs}] [{column_nodes}] observation',
             f'.model observation dac_bridge(out_low=0 out_high=5 out_undef={args.output_unknown_volts:g} t_rise=1n t_fall=1n)',
             # Save a tail window to avoid storing the entire power-on delay. Simulation
             # still begins at zero; no capacitor initial conditions or injected clock/reset.
             '.save ' + ' '.join([*trace_signals, supply_signal]),
             '.control', 'set wr_singlescale', 'set wr_vecnames',
             f'tran {args.step_ns}n {report["assumptions"]["traceWindowSeconds"][1]:.12g} 124m',
             'wrdata trace.txt ' + ' '.join(trace_signals),
             'wrdata supply-trace.txt ' + supply_signal,
             'quit', '.endc', '.end']
    if electrical_bus:
        signals = ' '.join(f'v(n_D{i})' for i in range(8)) + ' v(n_p5V)'
        lines.insert(lines.index('.control'), '.save ' + signals)
        lines.insert(lines.index('.control') + 1, 'set numdgt=17')
        lines.insert(lines.index('quit'), 'wrdata bus-trace.txt ' + signals)
    if electrical_wr:
        signals = f'v({node(report["wrCircuit"]["net"])}) v(wr_low) v(wr_high) @bwr_low[i] @bwr_high[i] v(n_p5V)'
        lines.insert(lines.index('.control'), '.save ' + signals)
        lines.insert(lines.index('quit'), 'wrdata wr-trace.txt ' + signals)
    deck = with_minimum_breakpoint('\n'.join(lines) + '\n', args.minimum_breakpoint_fs)
    (out / 'boot.cir').write_text(deck)
    report['deckSha256'] = sha(out / 'boot.cir')


def validate(out, report):
    log = (out / 'ngspice.log').read_text()
    if solver_diagnostic(log):
        raise ValueError('Solver/bridge diagnostics: inspect ngspice.log')
    if report['assumptions'].get('electricalBus'):
        rom = bytes(int(value, 16) for value in (out / 's600.hex').read_text().split())
        report['busObservation'] = measure_bus(log, out / 'bus-trace.txt',
            report['assumptions']['maximumStepNs'], rom,
            trace_extent=tuple(report['assumptions']['traceWindowSeconds']),
            start_tolerance_ns=report['assumptions']['maximumStepNs'])
        report['busQualification'] = 'Every logged read must have captured voltage; reads before the capture window fail. U880 phase timing and electrical device calibration remain unqualified.'
    if report['assumptions'].get('electricalWr'):
        first, last = report['assumptions']['traceWindowSeconds']
        report['wrObservation'] = measure_wr(log, out / 'wr-trace.txt',
            report['assumptions']['maximumStepNs'], last, start_seconds=first,
            capture_start_seconds=first, start_tolerance_ns=report['assumptions']['maximumStepNs'],
            require_activity=bool(report.get('scenario')))
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
    if 'supplyTraceSignal' in report:
        report['cpuClockVoltage'] = inspect_clock_voltage(
            out / 'trace.txt', out / 'supply-trace.txt', diagnostic_columns=2)
        report['cpuClockTiming'] = inspect_clock_timing(
            out / 'trace.txt', out / 'supply-trace.txt', report['assumptions']['maximumStepNs'], diagnostic_columns=2)
    else:
        report['cpuClockVoltage'] = {'qualified': False, 'unavailable': 'Legacy trace has no simultaneous supply samples'}
    report['firstFetchAfterRelease'] = after[0]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom', type=Path, required=True)
    p.add_argument('--bridge', type=Path, default=ROOT / 'build/keyboard-controller-analog/bridge/bridge.json')
    p.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-analog/coupled-boot')
    p.add_argument('--bypass-rom-bus', action='store_true', help='Diagnostic: feed ROM directly to CPU input')
    p.add_argument('--wr-only-data', action='store_true', help='Retain old WR-only data drive as a diagnostic control')
    p.add_argument('--electrical-outputs', action='store_true')
    p.add_argument('--electrical-cpu-pullups', action='store_true', help='Model R6.4/R6.5 and reference-maximum CPU input capacitance')
    p.add_argument('--electrical-logic-pullups', action='store_true', help='Couple latch and flip-flop control pullups through nominal electrical sinks')
    p.add_argument('--logic-load-pf', type=float, default=0, help='Illustrative added capacitance per logic-control net, not a device parameter')
    p.add_argument('--serial-driver', choices=('nominal', '7406-dc'), default='nominal',
                   help='Optional unqualified transistor serial gates; requires electrical outputs')
    p.add_argument('--output-unknown-volts', type=float, choices=(0, 2.5, 5), default=2.5,
                   help='Diagnostic uniform DAC voltage for HDL X outputs; not measured power-on behavior')
    p.add_argument('--minimum-breakpoint-fs', type=float,
                   help='Numerical breakpoint spacing retained using deck .tran/control run')
    p.add_argument('--electrical-matrix', action='store_true')
    p.add_argument('--contacts', default='', help='Comma-separated fixture contact indices held closed from power-on')
    p.add_argument('--scenario', type=Path, help='Contact recipe at 125 ms origin, 1 us wall-time ticks; requires electrical matrix and outputs')
    p.add_argument('--prepare-only', action='store_true', help='Generate inputs without claiming a simulation pass')
    p.add_argument('--compress-traces', action='store_true', help='Stream the boot waveform to lossless XZ in a fresh waveform directory')
    p.add_argument('--compression-preset', type=int, choices=range(10), default=1, help='Lossless XZ preset; higher values trade compression time and memory for storage')
    power = p.add_mutually_exclusive_group()
    power.add_argument('--supply-stimulus', type=Path, help='JSON pointsSecondsVolts host supply waveform; diagnostic power-dip/recovery input')
    power.add_argument('--rise-us', type=float, default=1)
    p.add_argument('--gate-profile', choices=tuple(GATE_MODELS), default='nominal')
    p.add_argument('--reset-load', choices=RESET_LOADS, default='illustrative')
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
    p.add_argument('--electrical-wr', action='store_true', help='Electrical WR output into transistor clock gate; requires electrical bus and transistor outputs')
    p.add_argument('--electrical-bus', action='store_true')
    p.add_argument('--latch-timing-envelope', action='store_true', help='Conservative Intel 8282 timing; requires electrical-bus')
    p.add_argument('--rom-read-envelope', action='store_true', help='Conservative Intel 2716 read timing; requires electrical-bus')
    p.add_argument('--cpu-profile', choices=CIRCUIT_PROFILES, default='tv80')
    p.add_argument('--bus-latch-pf', type=float)
    p.add_argument('--bus-7406-pf', type=float)
    args = p.parse_args()
    try:
        electrical_bus_options(args)
    except ValueError as error:
        p.error(str(error))
    if args.serial_driver != 'nominal' and not args.electrical_outputs:
        p.error('serial-driver requires electrical-outputs')
    if args.minimum_breakpoint_fs is not None and (not math.isfinite(args.minimum_breakpoint_fs) or args.minimum_breakpoint_fs <= 0):
        p.error('minimum-breakpoint-fs must be positive and finite')
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
    try:
        args.supply_data = supply_stimulus.load(args.supply_stimulus, stop) if args.supply_stimulus else None
    except (ValueError, OSError) as error:
        p.error(str(error))
    if not math.isfinite(args.logic_load_pf) or args.logic_load_pf < 0 or (args.logic_load_pf and not args.electrical_logic_pullups):
        p.error('logic-load-pf must be nonnegative and requires electrical-logic-pullups')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.compress_traces and any(out.glob('*trace.txt*')):
        p.error('Compressed capture requires a fresh waveform output directory')
    for name in ('report.json', 'trace.txt', 'supply-trace.txt', 'bus-trace.txt', 'wr-trace.txt', 'ngspice.log'):
        (out / name).unlink(missing_ok=True)
    report = {'passed': False, 'scope': __doc__,
              'assumptions': {'receiverThresholdVolts': 1.4,
                              'solver': {'reltol': args.reltol, 'vntol': args.vntol, 'abstol': args.abstol},
                              'receiver': 'Single nominal threshold avoids counting both edges of an X band as clock edges',
                              'analogModels': 'Nominal reset semiconductors and exploratory LS NAND; no specimen timing claim',
                              'latchLoad': args.latch_load, 'columnLoadPf': args.column_load_pf, 'npnProfile': args.npn_profile, 'gateProfile': args.gate_profile,
                              'serialReceiver': args.electrical_outputs,
                              'serialDriver': args.serial_driver,
                              'outputUnknownVolts': args.output_unknown_volts,
                              'minimumBreakpointFs': args.minimum_breakpoint_fs,
                              'analysisInvocation': 'deck-tran/run' if args.minimum_breakpoint_fs is not None else 'control-tran',
                              'remainingDigitalBoundaries': ([] if args.electrical_matrix else ['matrix sensing']) + ['CPU/peripheral buses'] + ([] if args.electrical_outputs else ['LED and serial output loading']),
                              'romBus': 'Direct CPU input diagnostic' if args.bypass_rom_bus else 'Resolved CPU/ROM/latch bus from numbered schematic pins',
                              'cpuDataDrive': 'WR-only diagnostic' if args.wr_only_data else 'TV80 write-cycle intent gated by reset and bus ownership',
                              'electricalOutputs': args.electrical_outputs, 'electricalMatrix': args.electrical_matrix, 'closedContacts': sorted(args.contacts),
                              'electricalCpuPullups': args.electrical_cpu_pullups,
                              'electricalLogicPullups': args.electrical_logic_pullups, 'logicLoadPf': args.logic_load_pf,
                              'logicControlReceivers': 'I/O-active clock uses nominal 1.4 V crossing; output-enable and async controls use 0.8/2 V unknown band',
                              'contacts': 'Static diode-free fixture in electrical mode; boot test, not firmware scenario qualification',
                              'traceWindowSeconds': [.124, stop], 'simulationStartSeconds': 0,
                              'bridgeDelayNs': args.bridge_delay_ns,
                              'bridgeDelay': 'Numerical synchronization only; not calibrated device propagation',
                              'maximumStepNs': args.step_ns, 'timeoutSeconds': args.timeout_seconds, 'supplyRiseUs': args.rise_us,
                              'knownLimit': 'The nominal model failed to produce a reset pulse with a 10 ns supply ramp'},
              'sources': {name: sha(HERE / name) for name in ('boot_cosim.py', 'boot_cosim.v',
                            'circuit.py', 'sc236_dc.cir', 'oscillator_probe.py', 'reset_probe.py',
                            GATE_MODELS[args.gate_profile], 'gate_models.py', 'clock_voltage.py', 'clock_timing.py', 'clock_convergence.py', 'cpu_clock_limits.json', 'cpu_control.py', 'logic_control.py',
                            'controller_interface.py', 'matrix.py', 'latch_limits.json', 'failure_evidence.py', 'ngspice_runtime.py', 'output_circuit.py', 'model_coverage.py',
                            'serial_observation.py', 'supply_stimulus.py', 'board_scenario.py', 'io_scenario.py', 'trace_io.py',
                            'transient_analysis.py', 'ttl7406_output_probe.py', 'ttl7406_nominal.cir', 'compressed_output.py')}}
    report['waveformCompression'] = {'format': 'xz', 'preset': args.compression_preset} if args.compress_traces else None
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
        trace_names = ['trace.txt', 'supply-trace.txt'] + (['bus-trace.txt'] if args.electrical_bus else [])
        if args.electrical_wr:
            trace_names.append('wr-trace.txt')
        with capture_compressed(out, trace_names, args.compress_traces, preset=args.compression_preset) as compressed:
            with (out / 'ngspice.log').open('w') as log:
                subprocess.run([engine, '-n', '-b', 'boot.cir'], cwd=out, env=engine_env, stdout=log,
                               stderr=subprocess.STDOUT, check=True, timeout=args.timeout_seconds)
        if args.compress_traces:
            report['compressedWaveforms'] = compressed
        verify_runtime(report['ngspiceRuntime'])
        report['logSha256'] = sha(out / 'ngspice.log')
        for name, key in [('trace.txt', 'traceSha256'), ('supply-trace.txt', 'supplyTraceSha256')]:
            report[key] = sha(out / name)
            if args.compress_traces and report[key] != compressed[name]['sha256']:
                raise ValueError('Compressed boot waveform differs from producer bytes: ' + name)
        if args.electrical_bus:
            report['busTraceSha256'] = sha(out / 'bus-trace.txt')
            if args.compress_traces and report['busTraceSha256'] != compressed['bus-trace.txt']['sha256']:
                raise ValueError('Compressed bus waveform differs from producer bytes')
        if args.electrical_wr:
            report['wrTraceSha256'] = sha(out / 'wr-trace.txt')
            if args.compress_traces and report['wrTraceSha256'] != compressed['wr-trace.txt']['sha256']:
                raise ValueError('Compressed WR waveform differs from producer bytes')
        validate(out, report)
        report['passed'] = True
    except Exception as error:
        if isinstance(error, WriteMismatch):
            report['wrFailure'] = error.details
        if isinstance(error, BusMismatch):
            report['busFailure'] = error.details
        if isinstance(error, SerialMismatch):
            report['serialFailure'] = error.details
        report['error'] = str(error)
        names = ['ngspice.log', 'trace.txt', 'supply-trace.txt'] + (['bus-trace.txt'] if args.electrical_bus else [])
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
