#!/usr/bin/env python3
"""Compile real board HDL and inspect prepared decks; no firmware execution claim."""
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from boot_cosim import prepare, sha
from qualify_board_pair import normalized_analysis


class BootPreparationTests(unittest.TestCase):
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
                report = {'assumptions': {'traceWindowSeconds': [.124, .127]}}
                with patch('boot_cosim.ROM_SHA256', fixture_sha):
                    prepare(args, report)
                deck = (out / 'boot.cir').read_text()
                if unknown == 2.5 and gate_profile == 'nominal':
                    decks[profile] = deck
                if gate_profile == 'dl000-pullup':
                    self.assertEqual(report['gateModel']['file'], 'ls_nand_pullup.cir')
                    self.assertIn('.include ls_nand_pullup.cir', deck)
                self.assertIn(f'out_undef={unknown:g} ', deck)
                self.assertIn(f'to {unknown:g} V', report['outputControlUnknowns'])
                self.assertTrue((out / 'boot.vvp').stat().st_size > 0)
                self.assertEqual(sha(out / 'boot.cir'), report['deckSha256'])
                self.assertIn('RBR1 ', deck)
                self.assertIn('RBR2 ', deck)
                self.assertIn('Ahdl ', deck)
                self.assertIn('0.127 124m', deck)
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


if __name__ == '__main__':
    unittest.main()
