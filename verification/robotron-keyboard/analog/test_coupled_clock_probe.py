#!/usr/bin/env python3
"""The early probe must preserve board topology and compare identical inputs."""
import copy
import json
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import tempfile
from pathlib import Path
from coupled_clock_probe import early_deck, matching_inputs, summarize_diagnostics, DIAGNOSTIC_SIGNALS, run, sha


class CoupledClockProbeTests(unittest.TestCase):
    def test_only_transient_window_changes(self):
        deck = 'fixture\nRBR1 a b .001\n.control\ntran 2n 0.127 124m\nwrdata trace.txt v(a)\n.endc\n.end\n'
        self.assertEqual(early_deck(deck, 2, 100), deck.replace('tran 2n 0.127 124m', 'tran 2n 100u'))
        for invalid in (deck.replace('2n', '5n'), deck.replace('124m', '123m'), deck + 'tran 2n 0.127 124m\n'):
            with self.assertRaises(ValueError):
                early_deck(invalid, 2, 100)

    def test_diagnostics_add_observation_without_changing_circuit(self):
        deck = 'fixture\nRBR1 a b .001\n.save v(a)\n.control\ntran 2n 0.127 124m\nwrdata trace.txt v(a)\n.endc\n.end\n'
        changed = early_deck(deck, 2, 100, ('v(b)',))
        self.assertIn('.save v(a) v(b)\n', changed)
        self.assertIn('wrdata trace.txt v(a)\nwrdata diagnostic-trace.txt v(b)', changed)
        self.assertIn('RBR1 a b .001\n', changed)
        with self.assertRaises(ValueError):
            early_deck(deck.replace('.save v(a)\n', ''), 2, 100, ('v(b)',))

    def test_diagnostic_endpoints_and_nonfinite_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'trace.txt'
            values = ' '.join(['1'] * len(DIAGNOSTIC_SIGNALS))
            valid = f'time signals\n0 {values}\n0.0001 {values}\n'
            path.write_text(valid)
            self.assertEqual(summarize_diagnostics(path, 100)['lastSeconds'], .0001)
            for bad in (valid.replace('0.0001', '0.00005'), valid.replace('0.0001', '-0.0001'), valid.replace('0.0001', 'nan')):
                path.write_text(bad)
                with self.assertRaises(ValueError):
                    summarize_diagnostics(path, 100)

    def test_aborted_solver_without_waveform_keeps_solver_reason(self):
        # ngspice can return zero after an aborted transient and write no trace.
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            args = SimpleNamespace(rom=directory / 's600.bin', gate_profile='nominal',
                                   rise_us=1, reltol=1e-9, vntol=1e-11, abstol=1e-17,
                                   duration_us=150, timeout_seconds=1)
            deck = ('fixture\n.save v(a)\n.control\ntran 1n 0.127 124m\n'
                    'wrdata trace.txt v(a)\n.endc\n.end\n')

            def execute(command, **kwargs):
                if '--prepare-only' in command:
                    (directory / 'boot.cir').write_text(deck)
                    (directory / 'report.json').write_text(json.dumps({
                        'passed': False, 'preparedOnly': True,
                        'deckSha256': sha(directory / 'boot.cir')}))
                else:
                    kwargs['stdout'].write('doAnalyses: TRAN: Timestep too small\n'
                                           'tran simulation(s) aborted\n')

            with patch('coupled_clock_probe.subprocess.run', side_effect=execute):
                with self.assertRaisesRegex(ValueError, 'Timestep too small'):
                    run(args, 1, directory)
            report = json.loads((directory / 'clock-probe.json').read_text())
            self.assertFalse(report['completed'])
            self.assertIn('Timestep too small', report['solverDiagnostic'])
            self.assertEqual(report['failureArtifacts']['trace.txt']['status'], 'missing')
            self.assertEqual(report['failureArtifacts']['ngspice.log']['sha256'],
                             sha(directory / 'ngspice.log'))

    def test_model_and_solver_changes_rejected(self):
        coarse = {key: 'same' for key in ('romSha256', 'connectivitySha256', 'bridge', 'tv80', 'ngspice', 'iverilog', 'sources')}
        coarse.update(assumptions={'maximumStepNs': 2, 'solver': {'reltol': 1e-7}}, hdlSha256={'/coarse/chips.v': 'same'})
        fine = copy.deepcopy(coarse)
        fine['assumptions']['maximumStepNs'] = 1
        fine['hdlSha256'] = {'/fine/chips.v': 'same'}
        matching_inputs(coarse, fine)
        for kind in ('sources', 'solver', 'hdl', 'duplicate'):
            changed = copy.deepcopy(fine)
            if kind == 'sources': changed['sources'] = 'changed'
            if kind == 'solver': changed['assumptions']['solver']['reltol'] = 1e-3
            if kind == 'hdl': changed['hdlSha256']['/fine/chips.v'] = 'changed'
            if kind == 'duplicate': changed['hdlSha256']['/elsewhere/chips.v'] = 'same'
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                matching_inputs(coarse, changed)


if __name__ == '__main__':
    unittest.main()
