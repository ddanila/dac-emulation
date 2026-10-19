"""Check passive winding modes against analytical impedance, including dot reversal."""
import math
import argparse
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from circuit import load, node
from output_circuit import CHOKE_REFS, choke_circuit, output_circuit, add_filter_options, filter_options
from ttl7406_output_probe import driver_circuit


class FilterTests(unittest.TestCase):
    def test_runner_filter_options_and_driver_paths(self):
        parser = argparse.ArgumentParser()
        add_filter_options(parser)
        components, _ = load()
        args = parser.parse_args(['--filter-coupling', '.8', '--filter-dot-pins', '1', '2', '1', '1'])
        options = filter_options(args)
        for profile in ('nominal', '7406-dc'):
            lines, metadata = driver_circuit(components, profile, 1000, **options)
            self.assertEqual(sum(line.startswith('Kfilter') for line in lines), 6)
            self.assertEqual(metadata['filter']['coupling'], .8)
            self.assertEqual(metadata['filter']['dotPins']['L1.2'], 2)
            self.assertFalse(metadata['filter']['qualified'])
            winding = next(line for line in lines if line.startswith('L1.2 '))
            self.assertEqual(winding.split()[1], 'L1_2_series')
        with self.assertRaisesRegex(ValueError, 'electrical outputs'):
            filter_options(args, enabled=False)
        for invalid in ('nan', 'inf', '-.1', '1'):
            args = parser.parse_args(['--filter-coupling', invalid])
            with self.assertRaises(ValueError):
                filter_options(args)
        args = parser.parse_args(['--filter-dot-pins', '1', '2', '3', '1'])
        with self.assertRaises(ValueError):
            filter_options(args)
        self.assertEqual(filter_options(parser.parse_args([]), enabled=False),
                         {'coupling': 0, 'dots': (1, 1, 1, 1)})

    def test_invalid_and_singular_hypotheses_rejected(self):
        components, _ = load()
        for k in (-.1, 1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                choke_circuit(components, coupling=k)
        for dots in ((1, 2), (1, 1, 1, 3), (True, 1, 1, 1)):
            with self.assertRaises(ValueError):
                choke_circuit(components, dots=dots)
        for value in (0, -1, float('nan')):
            with self.assertRaises(ValueError):
                choke_circuit(components, choke_uh=value)
            with self.assertRaises(ValueError):
                choke_circuit(components, choke_ohms=value)
        lines, metadata = output_circuit(components)
        self.assertFalse(any(line.startswith('Kfilter') for line in lines))
        self.assertFalse(metadata['filter']['qualified'])

    def test_common_and_differential_modes_and_dot_reversal(self):
        # Independent current excitation: V = (R I + j*omega*L) * current.
        components = {ref: {'type': 'CHOKE', 'pins': {'1': f'port{i}', '2': 'GND'}}
                      for i, ref in enumerate(CHOKE_REFS)}
        for k, dots, excitation in (
            (0, (1, 1, 1, 1), (1, 1, 1, 1)),
            (.8, (1, 1, 1, 1), (1, 1, 1, 1)),
            (.8, (1, 1, 1, 1), (1, -1, 1, -1)),
            (.8, (1, 2, 1, 1), (1, 1, 1, 1)),
        ):
            with self.subTest(k=k, dots=dots, excitation=excitation), tempfile.TemporaryDirectory() as temp:
                out = Path(temp)
                lines, _ = choke_circuit(components, coupling=k, dots=dots)
                signals = [f'v({node(f"port{i}")})' for i in range(4)]
                sources = [f'I{i} 0 {node(f"port{i}")} DC 0 AC {value}' for i, value in enumerate(excitation)]
                deck = ['Winding impedance test', f'Vground {node("GND")} 0 0', *lines, *sources, '.control',
                        'set wr_singlescale', 'set wr_vecnames', 'ac lin 1 1meg 1meg',
                        'wrdata trace.txt ' + ' '.join(signals), 'quit', '.endc', '.end']
                (out/'test.cir').write_text('\n'.join(deck)+'\n')
                proc = subprocess.run(['ngspice', '-n', '-b', 'test.cir'], cwd=out,
                                      capture_output=True, text=True, timeout=30)
                self.assertEqual(proc.returncode, 0, proc.stdout+proc.stderr)
                self.assertIsNone(re.search(r'warning|error|failed|singular', proc.stdout+proc.stderr, re.I), proc.stdout+proc.stderr)
                rows = (out/'trace.txt').read_text().splitlines()[1:]
                self.assertEqual(len(rows), 1)
                row = [float(x) for x in rows[0].split()]
                self.assertEqual(len(row), 9)
                self.assertTrue(all(map(math.isfinite, row)))
                self.assertEqual(row[0], 1e6)
                signs = [1 if pin == 1 else -1 for pin in dots]
                common = sum(s*a for s, a in zip(signs, excitation))
                for i, (sign, current) in enumerate(zip(signs, excitation)):
                    expected_imag = 2*math.pi*((1-k)*current + k*sign*common)
                    self.assertAlmostEqual(row[1+2*i], current, delta=1e-7)
                    self.assertAlmostEqual(row[2+2*i], expected_imag, delta=1e-6)


if __name__ == '__main__':
    unittest.main()
