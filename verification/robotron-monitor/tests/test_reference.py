import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import reference


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.inventory = json.loads((ROOT/'reference/k7222-11/inventory.json').read_text())
        self.profile = reference.read_profile(ROOT/'profiles/k7222-11-neck.json')

    def test_missing_and_unresolved_parts_prevent_qualification(self):
        report = reference.coverage(self.inventory, [])
        self.assertEqual(report['connected'], 0)
        self.assertIn('012-6921:T3', report['missing'])
        self.assertFalse(report['full_monitor_qualified'])
        self.assertIn('012-6931:C6', report['unresolved'])
        broken = copy.deepcopy(self.inventory)
        broken['parts'].append(broken['parts'][0])
        with self.assertRaises(ValueError): reference.inventory_check(broken)

    def test_uncertainty_requires_finite_in_range_values(self):
        for name,value in [('q_bf',0),('q_bf',float('nan')),('unknown',1),('neck_c2',2)]:
            with self.assertRaises(ValueError): reference.parameter_values(self.profile,{name:value})
        self.assertEqual(reference.parameter_values(self.profile,{'q_bf':20})['q_bf'],20)

    def test_reconciled_power_parts_do_not_invent_missing_values(self):
        parts={p['id']:p for p in self.inventory['parts']}
        self.assertEqual(len(parts),260)
        self.assertEqual(parts['012-6931:V22']['kind'],'bjt')
        self.assertNotIn('assembly:V22',parts)
        self.assertIsNone(parts['012-6931:C15']['value'])
        for ref,nf in [('C6',10),('C10',2.2),('C18',33),('C25',33)]:
            self.assertAlmostEqual(parts['012-6931:'+ref]['value']/1e-9,nf)
            self.assertEqual(parts['012-6931:'+ref]['evidence'],'inferred')

    def test_window_budget_and_truncated_samples(self):
        for start,stop,step in [(1,0,1e-6),(0,1,1e-9),(-1,.001,1e-7),(0,float('inf'),1e-6)]:
            with self.assertRaises(ValueError): reference.deck(self.profile,[],{},start,stop,step,'','')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'samples.txt'
            path.write_text('time v(a)\n0.1 1\n0.2 2\n')
            with self.assertRaises(ValueError): reference.read_samples(path,[{}],.1,.3,.1)


class NeckBenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        cls.profile_path = ROOT/'profiles/k7222-11-neck.json'
        cls.profile = reference.read_profile(cls.profile_path)
        cls.report = reference.run(cls.profile_path,cls.directory/'baseline',step=2e-7)
        cls.rows = reference.read_samples(cls.directory/'baseline/samples.txt',cls.profile['probes'],0,.0004,2e-7)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def at(self,rows,t): return min(rows,key=lambda row:abs(row[0]-t))

    def test_original_neck_network_and_intensity_polarity(self):
        components = {c['source_id']:c for c in self.report['components']}
        # Independent source schematic constraints: Baker clamp and intensity diode.
        self.assertEqual(components['012-6891:V2:2']['nodes'],['clamp','collector'])
        self.assertEqual(components['012-6891:V2:4']['nodes'],['intens','brightness'])
        self.assertEqual(components['012-6891:V2:6']['nodes'],['tail','collector'])
        expected = {p['id'] for p in json.loads((ROOT/'reference/k7222-11/inventory.json').read_text())['parts'] if p['board']=='012-6891'}
        self.assertEqual(set(components), expected)
        dark,bright,dark2,normal = [self.at(self.rows,t)[4] for t in (50e-6,150e-6,250e-6,350e-6)]
        self.assertGreater(dark,30)
        self.assertAlmostEqual(dark,dark2,delta=.1)
        self.assertLess(bright,1)
        self.assertGreater(normal,bright+2)
        self.assertLess(normal,6)
        self.assertFalse(self.report['coverage']['full_monitor_qualified'])

    def test_refinement_and_absolute_recording_window(self):
        reference.run(self.profile_path,self.directory/'refined',start=.0001,step=1e-7)
        refined=reference.read_samples(self.directory/'refined/samples.txt',self.profile['probes'],.0001,.0004,1e-7)
        for t in (150e-6,250e-6,350e-6):
            a,b=self.at(self.rows,t),self.at(refined,t)
            for va,vb in zip(a[1:],b[1:]): self.assertLess(abs(va-vb),max(.001,abs(vb)*.01))
        data=(self.directory/'refined/replay.mcrt').read_bytes()
        self.assertEqual(data[:8],b'DACCRT2\n')
        size=struct.unpack_from('<I',data,8)[0]
        meta=json.loads(data[12:12+size])
        self.assertAlmostEqual(meta['start_time'],.0001)
        self.assertAlmostEqual(meta['duration'],.0003)
        self.assertEqual(meta['solver']['simulated_from_s'],0)

    def test_gain_bound_still_switches_and_provenance_records_override(self):
        report=reference.run(self.profile_path,self.directory/'low-gain',step=2e-7,changes={'q_bf':20})
        rows=reference.read_samples(self.directory/'low-gain/samples.txt',self.profile['probes'],0,.0004,2e-7)
        self.assertLess(self.at(rows,150e-6)[4],self.at(rows,50e-6)[4]-20)
        self.assertEqual(report['parameters']['q_bf'],20)
        self.assertEqual(report['uncertainty']['q_bf']['nominal'],26)
        with self.assertRaises(FileExistsError): reference.run(self.profile_path,self.directory/'low-gain')


if __name__ == '__main__': unittest.main()
