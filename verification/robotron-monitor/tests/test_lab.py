import importlib.util
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import lab
from optics import DEFAULTS, landing, deposit


class OpticsTests(unittest.TestCase):
    def test_deflection_polarity_and_acceleration(self):
        a = landing(10000, 1200, .2, 0)
        b = landing(10000, 1200, -.2, 0)
        c = landing(20000, 2400, .2, 0)
        self.assertTrue(a[3])
        self.assertAlmostEqual(a[0], -b[0], places=12)
        self.assertLess(abs(c[0]), abs(a[0]))
        self.assertAlmostEqual(a[0]/c[0], math.sqrt(2), delta=.015)
        self.assertFalse(landing(0, 0, 0, 0)[3])

    def test_focus_and_energy(self):
        nominal = landing(10000, 1200, 0, 0)
        defocused = landing(10000, 3000, 0, 0)
        self.assertGreater(defocused[2], nominal[2])
        screen = [0.]*(160*112)
        energy = deposit(screen,160,112,0,0,.001,1e-6)
        self.assertAlmostEqual(energy,1e-6,places=16)
        self.assertAlmostEqual(sum(screen),1e-6,places=16)
        with self.assertRaises(ValueError):
            landing(float('nan'),1,1,1)

    def test_phosphor_dark_decay_and_energy_budget(self):
        # Centered illuminated sample followed by darkness. Optical decay is
        # independent of the host rendering rate and never creates energy.
        rows = [[0,0,10000,1200,0,0,0,0], [.001,0,10000,1200,0,0,0,1e-8],
                [.026,0,10000,1200,0,0,0,0]]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'replay.mcrt'
            report=lab.package(rows,{},path)
            self.assertLessEqual(report['energy']['deposited_light_j'],report['energy']['beam_j']*DEFAULTS['light_efficiency']*1.0000001)
            data=path.read_bytes();base=12+struct.unpack_from('<I',data,8)[0]
            first,last=report['chunks'][1:3]
            values=[]
            for chunk in (first,last):
                pixels=data[base+chunk['offset']:base+chunk['offset']+chunk['bytes']]
                # Invert the display exposure at the brightest pixel.
                values.append(-math.log(1-max(pixels)/255))
            self.assertAlmostEqual(values[1]/values[0],math.exp(-1),delta=.06)


class CaptureTests(unittest.TestCase):
    def test_capture_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'input.json'
            data={'format':'dac-monitor-input-v1','clock_hz':1000,'events':[[0,0,1,0],[1,1,1,0],[5,0,0,0]]}
            path.write_text(json.dumps(data));self.assertEqual(lab.parse_capture(path),data)
            for events in ([[0,0,1,0],[0,1,1,0]], [[1,0,1,0],[2,1,1,0]], [[0,0,1,0],[1,2,1,0]]):
                data['events']=events;path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):lab.parse_capture(path)


class ElectricalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.directory=Path(cls.temp.name)
        subprocess.run(['kicad-cli','sch','export','netlist','--format','kicadxml','-o',str(cls.directory/'net.xml'),str(ROOT/'circuits/fixture.kicad_sch')],check=True,capture_output=True)
        cls.components=lab.connectivity(cls.directory/'net.xml')

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def solve(self,name,changes=None,step=1e-6):
        directory=self.directory/name;directory.mkdir()
        deck=lab.build_deck(self.components,(ROOT/'circuits/fixture-models.cir').read_text(),.003,step,changes or {})
        (directory/'run.cir').write_text(deck)
        log=lab.run_command(['ngspice','-b','run.cir'],directory,directory/'log.txt')
        self.assertNotIn('Error:',log)
        return lab.samples(directory/'samples.txt',.003)

    def test_export_is_connected_and_numbered(self):
        by_ref={c['reference']:c for c in self.components}
        self.assertEqual(by_ref['Q1']['nodes'],['collector','base','0'])
        self.assertEqual(by_ref['L1']['nodes'],['bplus','collector'])
        self.assertEqual(by_ref['B1']['nodes'],['anode','cathode'])
        self.assertEqual(len(by_ref),30)
        with self.assertRaises(ValueError):lab.build_deck(self.components,'',.001,1e-6,{'R999':'10'})

    def test_circuit_changes_and_step_refinement(self):
        baseline=self.solve('baseline')
        collapse=self.solve('collapse',{'V3':'0'})
        load=self.solve('load',{'R3':'100k'})
        refined=self.solve('refined',step=.5e-6)
        self.assertGreater(max(r[2] for r in baseline),1000)
        self.assertGreater(max(abs(r[5]) for r in baseline),.1)
        self.assertLess(max(abs(r[5]) for r in collapse),1e-6)
        self.assertLess(load[-1][2],baseline[-1][2]*.95)
        # Compare EHT envelope, not an arbitrarily phase-aligned switch edge.
        self.assertAlmostEqual(refined[-1][2],baseline[-1][2],delta=baseline[-1][2]*.01)

    def test_incomplete_and_nan_samples_rejected(self):
        path=self.directory/'broken.txt'
        for content in ('header\n0 0 0 0 0 0 0 0\n', 'header\n0 nan 0 0 0 0 0 0\n'):
            path.write_text(content)
            with self.assertRaises(ValueError):lab.samples(path,.003)


if __name__=='__main__':unittest.main()
