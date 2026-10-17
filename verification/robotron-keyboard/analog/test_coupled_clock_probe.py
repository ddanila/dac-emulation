#!/usr/bin/env python3
"""The early probe must preserve board topology and compare identical inputs."""
import copy
import json
import hashlib
import lzma
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import tempfile
from pathlib import Path
from coupled_clock_probe import early_deck, matching_inputs, matching_runs, summarize_diagnostics, DIAGNOSTIC_SIGNALS, run, sha, waveform_sha


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

    def test_explicit_breakpoint_uses_default_task_and_preserves_wiring(self):
        deck = 'fixture\nRBR1 a b .001\n.control\ntran 2n 0.127 124m\nwrdata trace.txt v(a)\n.endc\n.end\n'
        changed = early_deck(deck, 2, 100, minimum_breakpoint_fs=1)
        self.assertIn('RBR1 a b .001\n.options minbreak=1f\n.tran 2n 100u\n.control\nrun\n', changed)
        self.assertNotIn('\ntran ', changed)
        for bad in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                early_deck(deck, 2, 100, minimum_breakpoint_fs=bad)
        for extra in ('.tran 1n 100u\n', '.options minbreak=2f\n'):
            with self.assertRaises(ValueError):
                early_deck(deck.replace('.control', extra + '.control'), 2, 100, minimum_breakpoint_fs=1)

    def test_breakpoint_mismatch_rejected_before_comparing_board(self):
        coarse = {'minimumBreakpointFs': 1, 'analysisInvocation': 'deck-tran/run', 'preparedBoard': {}}
        for field, different in [('minimumBreakpointFs', .1), ('analysisInvocation', 'control-tran')]:
            fine = dict(coarse, **{field: different})
            with patch('coupled_clock_probe.matching_inputs') as compare:
                with self.assertRaisesRegex(ValueError, 'solver settings differ'):
                    matching_runs(coarse, fine)
                compare.assert_not_called()

    def test_diagnostic_endpoints_and_nonfinite_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'trace.txt'
            values = ' '.join(['1'] * len(DIAGNOSTIC_SIGNALS))
            valid = f'time signals\n0 {values}\n0.0001 {values}\n'
            path.write_text(valid)
            self.assertEqual(summarize_diagnostics(path, 100)['lastSeconds'], .0001)
            Path(str(path) + '.xz').write_bytes(lzma.compress(valid.encode()))
            path.unlink()
            self.assertEqual(summarize_diagnostics(path, 100)['lastSeconds'], .0001)
            self.assertEqual(waveform_sha(path), hashlib.sha256(valid.encode()).hexdigest())
            for bad in (valid.replace('0.0001', '0.00005'), valid.replace('0.0001', '-0.0001'), valid.replace('0.0001', 'nan')):
                path.write_text(bad)
                with self.assertRaises(ValueError):
                    summarize_diagnostics(path, 100)

    def test_unlabelled_time_diagnostic_without_waveform_keeps_reason(self):
        # ngspice can return zero after an aborted transient and write no trace.
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            args = SimpleNamespace(rom=directory / 's600.bin', gate_profile='nominal',
                                   rise_us=1, reltol=1e-9, vntol=1e-11, abstol=1e-17,
                                   duration_us=150, timeout_seconds=1, column_load_pf=0, ngspice='ngspice', ngspice_spinit=None)
            deck = ('fixture\n.save v(a)\n.control\ntran 1n 0.127 124m\n'
                    'wrdata trace.txt v(a)\n.endc\n.end\n')

            from ngspice_runtime import identify
            executable = directory / 'fake-ngspice'
            executable.write_text('#!/bin/sh\nexit 0\n')
            executable.chmod(0o755)
            model = directory / 'digital.cm'
            model.write_text('fixture')
            init = directory / 'spinit'
            init.write_text(f'codemodel {model}\n')
            runtime, _ = identify(executable, init)

            def execute(command, **kwargs):
                if '--prepare-only' in command:
                    (directory / 'boot.cir').write_text(deck)
                    (directory / 'report.json').write_text(json.dumps({
                        'passed': False, 'preparedOnly': True,
                        'deckSha256': sha(directory / 'boot.cir'), 'ngspiceRuntime': runtime}))
                else:
                    kwargs['stdout'].write('Instance: ahdl   Message: XSPICE time is behind vtime:\n'
                                           'XSPICE 0.043\nCosim 0.043\n')

            with patch('coupled_clock_probe.subprocess.run', side_effect=execute):
                with self.assertRaisesRegex(ValueError, 'behind vtime'):
                    run(args, 1, directory)
            report = json.loads((directory / 'clock-probe.json').read_text())
            self.assertFalse(report['completed'])
            self.assertIn('behind vtime', report['solverDiagnostic'])
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
        for kind in ('sources', 'solver', 'hdl', 'duplicate', 'column_load', 'runtime', 'unknown_voltage'):
            changed = copy.deepcopy(fine)
            if kind == 'runtime': changed['ngspiceRuntime'] = {'codeModels': ['different']}
            if kind == 'unknown_voltage': changed['assumptions']['outputUnknownVolts'] = 0
            if kind == 'column_load': changed['assumptions']['columnLoadPf'] = 1
            if kind == 'sources': changed['sources'] = 'changed'
            if kind == 'solver': changed['assumptions']['solver']['reltol'] = 1e-3
            if kind == 'hdl': changed['hdlSha256']['/fine/chips.v'] = 'changed'
            if kind == 'duplicate': changed['hdlSha256']['/elsewhere/chips.v'] = 'same'
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                matching_inputs(coarse, changed)


if __name__ == '__main__':
    unittest.main()
