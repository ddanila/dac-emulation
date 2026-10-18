"""Verify passive host loading against an independent impedance calculation."""
import cmath
import math
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from host_receiver import host_receiver


class HostReceiverTests(unittest.TestCase):
    def test_loaded_filter_transfer(self):
        outputs = {'hostGround': 'cable_gnd', 'hostSupply': 'cable_5v',
                   'serial': {'data': {'cable': 'cable_data'}, 'clock': {'cable': 'cable_clock'}}}
        lines, info = host_receiver(outputs)
        self.assertFalse(info['qualified'])
        for frequency in (1e5, 1e6):
            with self.subTest(frequency=frequency), tempfile.TemporaryDirectory() as temp:
                p = Path(temp)
                deck = ['Host filter transfer', *lines,
                        f'Vground {info["ground"]} 0 0', f'Vsupply {info["supply"]} 0 0',
                        'Vdata cable_data 0 DC 0 AC 1', 'Vclock cable_clock 0 0',
                        '.control', 'set wr_singlescale', 'set wr_vecnames', 'set numdgt=17',
                        f'ac lin 1 {frequency} {frequency}',
                        f'wrdata trace.txt v({info["inputs"]["data"]}) v({info["inputs"]["clock"]})',
                        'quit', '.endc', '.end']
                (p/'test.cir').write_text('\n'.join(deck)+'\n')
                run = subprocess.run(['ngspice', '-n', '-b', 'test.cir'], cwd=p,
                                     capture_output=True, text=True, timeout=30)
                self.assertEqual(run.returncode, 0, run.stdout+run.stderr)
                self.assertIsNone(re.search(r'warning|error|failed|singular',run.stdout+run.stderr,re.I),run.stdout+run.stderr)
                rows = (p/'trace.txt').read_text().splitlines()[1:]
                self.assertEqual(len(rows),1)
                values = list(map(float,rows[0].split()))
                self.assertEqual(len(values),5)
                self.assertTrue(all(map(math.isfinite,values)))
                zc = 1/(2j*math.pi*frequency*680e-12)
                parallel = 1/(1/560 + 1/(100+zc))
                expected = parallel/(parallel+1+2j*math.pi*frequency*1e-6)*zc/(100+zc)
                self.assertLess(abs(complex(*values[1:3])-expected),1e-10)
                self.assertLess(abs(complex(*values[3:5])),1e-12)
        for bad in (0,-1,float('nan')):
            with self.assertRaises(ValueError):host_receiver(outputs,inductance_uh=bad)


if __name__ == '__main__':unittest.main()
