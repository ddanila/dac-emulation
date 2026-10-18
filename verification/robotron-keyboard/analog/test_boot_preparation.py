#!/usr/bin/env python3
"""Compile real board HDL and inspect prepared decks; no firmware execution claim."""
import hashlib
import json
from pathlib import Path
import tempfile
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from boot_cosim import prepare, sha, ROOT, electrical_bus_options
from qualify_board_pair import normalized_analysis, compare


class BootPreparationTests(unittest.TestCase):
    def test_electrical_bus_in_closed_board(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            library = out / 'preparation-only-library'
            library.write_bytes(b'not executable')
            bridge = out / 'bridge.json'
            bridge.write_text(json.dumps({'libraries': {
                key: {'path': str(library), 'sha256': sha(library)}
                for key in ('shim', 'libvvp', 'vpi')}}))
            rom = out / 'fixture.bin'
            rom.write_bytes(bytes(2048))
            args = SimpleNamespace(out=out, rom=rom, bridge=bridge, iverilog='iverilog',
                electrical_matrix=True, electrical_outputs=True, electrical_bus=True,
                bus_latch_pf=12, bus_7406_pf=3, wr_only_data=False, bypass_rom_bus=False,
                gate_profile='nominal', npn_profile='generic', latch_load='ideal', column_load_pf=0,
                scenario_data=None, contacts=set(), rise_us=1, reltol=.001, vntol=1e-6, abstol=1e-12,
                bridge_delay_ns=10, step_ns=5, serial_driver='7406-dc', minimum_breakpoint_fs=1,
                output_unknown_volts=2.5)
            report = {'assumptions': {'traceWindowSeconds': [.124, .127]}}
            with patch('boot_cosim.ROM_SHA256', sha(rom)):
                prepare(args, report)
            deck = (out / 'boot.cir').read_text()
            self.assertIn('RBR1 ', deck)
            self.assertIn('RBR2 ', deck)
            self.assertIn('Ain [n_CLK n_RESET_N] [dclk drst] receiver', deck)
            self.assertIn('drst drst drst dbus7 dbus6 dbus5 dbus4 dbus3 dbus2 dbus1 dbus0] [dbus_low23', deck)
            self.assertIn('dbus_high0 dsink csink', deck)
            self.assertIn('Xdata n_D0 ', deck)
            self.assertIn('Xclock clock_intent ', deck)
            self.assertIn('wrdata bus-trace.txt v(n_D0)', deck)
            self.assertTrue(report['assumptions']['electricalBus'])
            self.assertIn('bus_observation.py', report['sources'])
            with self.assertRaisesRegex(ValueError, 'timing qualification'):
                compare(report, report, 10)
            for name, value in (('electrical_matrix', False), ('bypass_rom_bus', True),
                                ('wr_only_data', True), ('bus_latch_pf', None), ('bus_7406_pf', float('nan'))):
                original = getattr(args, name)
                setattr(args, name, value)
                with self.assertRaises(ValueError):
                    electrical_bus_options(args)
                setattr(args, name, original)
            args.electrical_wr = True
            wr_report = {'assumptions': {'traceWindowSeconds': [.124, .127]}}
            with patch('boot_cosim.ROM_SHA256', sha(rom)):
                prepare(args, wr_report)
            deck = (out / 'boot.cir').read_text()
            self.assertIn('dbus_high0 dwr_low dwr_high dsink csink', deck)
            self.assertIn('Awr_drive [dwr_low dwr_high] [wr_low wr_high] observation', deck)
            self.assertIn('Xclock n_WR_N ', deck)
            self.assertNotIn('Xclock clock_intent ', deck)
            self.assertIn('wrdata wr-trace.txt v(n_WR_N)', deck)
            self.assertTrue(wr_report['assumptions']['electricalWr'])
            args.cpu_profile = 'falling-indexed-candidate'
            args.rom_read_envelope = True
            candidate_report = {'assumptions': {'traceWindowSeconds': [.124, .127]}}
            with patch('boot_cosim.ROM_SHA256', sha(rom)):
                prepare(args, candidate_report)
            self.assertEqual(candidate_report['assumptions']['cpuProfile'], args.cpu_profile)
            self.assertEqual(candidate_report['cpuModel']['profile'], args.cpu_profile)
            self.assertTrue(candidate_report['assumptions']['romReadEnvelope'])
            self.assertIn('eprom2716.v', candidate_report['sources'])
            self.assertIn('eprom2716_read_envelope rom_access', (out / 'controller_analog.v').read_text())
            self.assertIn('cpu_read_phase_candidate.py', candidate_report['sources'])
            self.assertIn('cpu.delayed_read', (out / 'controller_analog.v').read_text())
            self.assertIn('candidate_tv80_core.v', candidate_report['cpuModel']['generatedSha256'])
            self.assertNotIn('third_party/cpu/tv80/tv80_core.v', candidate_report['hdlSha256'])
            for name, value in (('electrical_outputs', False), ('serial_driver', 'nominal'),
                                ('electrical_bus', False)):
                original = getattr(args, name)
                setattr(args, name, value)
                with self.assertRaises(ValueError):
                    electrical_bus_options(args)
                setattr(args, name, original)

    def test_driver_selection_preserves_boot_and_closed_bridges(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            # Preparation never loads these libraries. Runtime provenance and
            # actual S600 execution are tested separately with the real bridge.
            library = root / 'preparation-only-library'
            library.write_bytes(b'not an executable library')
            bridge = root / 'bridge.json'
            bridge.write_text(json.dumps({'libraries': {
                key: {'path': str(library), 'sha256': sha(library)}
                for key in ('shim', 'libvvp', 'vpi')}}))
            rom = root / 'fixture.bin'
            rom.write_bytes(bytes(2048))
            fixture_sha = hashlib.sha256(rom.read_bytes()).hexdigest()
            decks = {}
            for profile, breakpoint_fs, unknown, gate_profile in (
                    ('nominal', None, 2.5, 'nominal'), ('7406-dc', 1, 2.5, 'nominal'),
                    ('nominal', 1, 0, 'nominal'), ('nominal', 1, 5, 'nominal'),
                    ('7406-dc', 1, 2.5, 'dl000-pullup')):
                out = root / f'{profile}-{unknown}-{gate_profile}'
                out.mkdir()
                args = SimpleNamespace(
                    out=out, rom=rom, bridge=bridge, iverilog='iverilog',
                    electrical_matrix=True, electrical_outputs=True,
                    wr_only_data=False, bypass_rom_bus=False, gate_profile=gate_profile,
                    npn_profile='generic', latch_load='ideal', column_load_pf=0,
                    scenario_data=None, contacts=set(), rise_us=1, reltol=.001,
                    vntol=1e-6, abstol=1e-12, bridge_delay_ns=10, step_ns=2,
                    serial_driver=profile, minimum_breakpoint_fs=breakpoint_fs,
                    output_unknown_volts=unknown)
                args.electrical_cpu_pullups = gate_profile == 'dl000-pullup'
                args.electrical_logic_pullups = gate_profile == 'dl000-pullup'
                args.logic_load_pf = 10 if args.electrical_logic_pullups else 0
                report = {'assumptions': {'traceWindowSeconds': [.124, .127]}}
                with patch('boot_cosim.ROM_SHA256', fixture_sha):
                    prepare(args, report)
                deck = (out / 'boot.cir').read_text()
                if unknown == 2.5 and gate_profile == 'nominal':
                    decks[profile] = deck
                if gate_profile == 'dl000-pullup':
                    self.assertEqual(report['gateModel']['file'], 'ls_nand_pullup.cir')
                    self.assertIn('.include ls_nand_pullup.cir', deck)
                    self.assertIn('R6.4 n_p5V n_CPU_PULLUP 1k', deck)
                    self.assertIn('R6.5 n_p5V n_BUSRQ_N 1k', deck)
                    self.assertIn('Acontrol [n_CPU_PULLUP n_BUSRQ_N] [dcontrol dbusrq] sense_receiver', deck)
                    self.assertIn('rx_clock dcontrol dbusrq dlogic_io dlogic_ff dlogic_oe]', deck)
                    self.assertEqual(report['modelCoverage']['components']['R6.4']['domain'], 'electrical')
                    for ref in ('R6.3', 'R6.6', 'R9.9'):
                        self.assertEqual(report['modelCoverage']['components'][ref]['domain'], 'electrical')
                    self.assertIn('Alogic_clock [n_IO_ACTIVE] [dlogic_io] receiver', deck)
                    self.assertEqual(report['logicControlCircuit']['fixtureLoadPfPerNet'], 10)
                else:
                    self.assertNotIn('Acontrol ', deck)
                    self.assertIn('rx_clock drst drst drst drst drst]', deck)
                self.assertIn(f'out_undef={unknown:g} ', deck)
                self.assertIn(f'to {unknown:g} V', report['outputControlUnknowns'])
                self.assertTrue((out / 'boot.vvp').stat().st_size > 0)
                self.assertEqual(sha(out / 'boot.cir'), report['deckSha256'])
                self.assertIn('RBR1 ', deck)
                self.assertIn('RBR2 ', deck)
                self.assertIn('Ahdl ', deck)
                self.assertIn('0.127 124m', deck)
                self.assertEqual(report['supplyTraceSignal'], 'v(n_p5V)')
                self.assertIn('wrdata supply-trace.txt v(n_p5V)\n', deck)
                self.assertIn('v(n_p5V)', next(line for line in deck.splitlines() if line.startswith('.save ')))
                self.assertEqual(report['romSha256'], fixture_sha)
                normalized_analysis(deck, {
                    'maximumStepNs': 2, 'minimumBreakpointFs': breakpoint_fs,
                    'analysisInvocation': 'control-tran' if breakpoint_fs is None else 'deck-tran/run'})
                if profile == '7406-dc':
                    self.assertIn('serialDriverDCReferenceSha256', report)
                    self.assertFalse(report['outputCircuit']['serialDriver']['modelQualified'])
                    self.assertIn('other gates remain digital', report['modelCoverage']['components']['A1']['model'])
            self.assertIn('Sdata ', decks['nominal'])
            self.assertNotIn('Xdata ', decks['nominal'])
            self.assertIn('Xdata ', decks['7406-dc'])
            self.assertIn('Xclock ', decks['7406-dc'])
            self.assertNotIn('OUTPUT_SINK_NOMINAL', decks['7406-dc'])
            self.assertIn('Vdriver_supply n_p5V driver_vp 0', decks['7406-dc'])
            # Exercise the real TV80 input connections, including X propagation.
            bench = out / 'control_check.v'
            bench.write_text('''`timescale 1ns/1ps
module control_check;
 reg control_n=0, request_n=1;
 boot_cosim #(.ELECTRICAL_CPU_PULLUPS(1)) dut(
  .clk(1'b0), .reset_n(1'b0), .sense(8'b0),
  .cpu_pullup_n(control_n), .bus_request_n(request_n));
 boot_cosim legacy(.clk(1'b0), .reset_n(1'b0), .sense(8'b0),
  .cpu_pullup_n(control_n), .bus_request_n(request_n));
 task check;
 begin
  #1;
  if(dut.cpu.wait_n !== control_n || dut.cpu.int_n !== control_n ||
     dut.cpu.nmi_n !== control_n || dut.cpu.busrq_n !== request_n)
    $fatal(1, "Electrical control input lost or swapped");
  if(legacy.cpu.wait_n !== 1'b1 || legacy.cpu.int_n !== 1'b1 ||
     legacy.cpu.nmi_n !== 1'b1 || legacy.cpu.busrq_n !== 1'b1)
    $fatal(1, "Legacy input boundary changed");
 end
 endtask
 initial begin
  check;
  control_n=1; request_n=0; check;
  control_n=1'bx; request_n=1'bx; check;
  $display("CONTROL_INPUTS_OK"); $finish;
 end
endmodule
''')
            hdl = [Path(name) if Path(name).is_absolute() else ROOT / name for name in report['hdlSha256']]
            subprocess.run(['iverilog', '-g2012', '-s', 'control_check', '-o', str(out / 'control-check.vvp'),
                            *map(str, hdl), str(bench)], check=True, capture_output=True, text=True)
            result = subprocess.run(['vvp', 'control-check.vvp'], cwd=out, check=True, capture_output=True, text=True)
            self.assertIn('CONTROL_INPUTS_OK', result.stdout)


if __name__ == '__main__':
    unittest.main()
