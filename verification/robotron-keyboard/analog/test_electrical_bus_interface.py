#!/usr/bin/env python3
"""Check independent drive intent and voltage-derived reads with the real chip HDL."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from electrical_bus_interface import generate

HERE = Path(__file__).resolve().parent


class ElectricalBusInterfaceTests(unittest.TestCase):
    def test_independent_drivers_and_receiver_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / 'controller.v').write_text(generate())
            subprocess.run(['iverilog', '-g2012', '-s', 'electrical_bus_tb',
                            '-o', str(out / 'bus.vvp'), str(out / 'controller.v'),
                            str(HERE.parent / 'chips.v'), str(HERE / 'electrical_bus_tb.v')], check=True)
            result = subprocess.run(['vvp', str(out / 'bus.vvp')],
                                    capture_output=True, text=True, check=True, timeout=30)
            self.assertIn('ELECTRICAL_BUS_INTERFACE_PASS', result.stdout)


if __name__ == '__main__':
    unittest.main()
