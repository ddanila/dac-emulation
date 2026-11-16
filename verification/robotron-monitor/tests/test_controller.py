"""Manufacturer-point checks for a provisional functional controller model."""
from pathlib import Path
import re
import json
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import lab
import reference
import author_schematic


class ControllerTests(unittest.TestCase):
    def solve(self, *, timing_c=6.4e-9, feedback=3.69, enable=8.4,
              modulation=8.4, current_sense=0, supply=12, step=1e-7):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            circuit = f'''TDA1060 characterization; not a historical converter
Vinput supply 0 PWL(0 0 50u {supply})
Rqc supply qc 100
Rload qe 0 100
Vfeedback fb 0 {feedback}
Vdfm dfm_level 0 4
Ven en 0 {enable}
Vmod modulation 0 {modulation}
Vcm cm 0 {current_sense}
Rtim rx 0 6400
Ctim cx 0 {timing_c}
Cga ga 0 22n
Xcontrol supply vz fb ga modulation dfm_level rx cx vz en cm 0 0 qe qc 0 TDA1060_FUNCTIONAL
'''
            profile = dict(name='controller characterization', subcircuits={'TDA1060_FUNCTIONAL':16},
                           probes=[dict(expression='v(cx)'), dict(expression='v(qe)'), dict(expression='v(ga)')])
            # reference.deck includes a title; keep circuit's title as a comment.
            deck = reference.deck(profile, [], {}, 0, .0008, step,
                                  (ROOT/'devices/tda1060.cir').read_text(), '* '+circuit)
            (directory/'run.cir').write_text(deck)
            log = lab.run_command(['ngspice','-b','run.cir'], directory, directory/'solver.log')
            self.assertIsNone(re.search(r'error|timestep too small|run simulation.*aborted',log,re.I),log)
            rows = reference.read_samples(directory/'samples.txt',profile['probes'],0,.0008,step)
            selected = [r for r in rows if r[0]>.0005]
            edges = [a[0]+(3.5-a[1])/(b[1]-a[1])*(b[0]-a[0])
                     for a,b in zip(selected,selected[1:]) if a[1]<3.5<=b[1]]
            return dict(frequency=(len(edges)-1)/(edges[-1]-edges[0]) if len(edges)>1 else 0,
                        duty=sum(r[2]>2 for r in selected)/len(selected),
                        peak=max(r[2] for r in selected), low=min(r[1] for r in selected),
                        high=max(r[1] for r in selected))

    def test_manufacturer_frequency_timing_scaling_and_refinement(self):
        nominal = self.solve()
        refined = self.solve(step=5e-8)
        double_c = self.solve(timing_c=12.8e-9)
        self.assertAlmostEqual(nominal['frequency'],30500,delta=305)
        self.assertAlmostEqual(double_c['frequency'],15250,delta=153)
        self.assertAlmostEqual(nominal['frequency'],refined['frequency'],delta=30.5)
        self.assertAlmostEqual(nominal['duty'],refined['duty'],delta=.005)
        self.assertAlmostEqual(nominal['low'],1.3,delta=.03)
        self.assertAlmostEqual(nominal['high'],5.7,delta=.03)
        self.assertTrue(.1<nominal['duty']<.8)
        self.assertTrue(3.8<nominal['peak']<5)

    def test_feedback_modulation_enable_and_inhibit(self):
        for changes in [dict(feedback=3.8),dict(enable=0),dict(modulation=0),
                        dict(current_sense=.7),dict(supply=8)]:
            with self.subTest(changes=changes):
                result=self.solve(**changes)
                self.assertLess(result['peak'],.01)
                self.assertEqual(result['duty'],0)


class SubcircuitContractTests(unittest.TestCase):
    def test_kicad_export_preserves_controller_source_and_pin_order(self):
        nodes = 'vcc vz fb ga modulation dfm rx cx syn en cm 0 sat qe qc fw'.split()
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            sheet = directory/'controller.kicad_sch'
            author_schematic.write(sheet, [dict(reference='X1', value='TDA1060_FUNCTIONAL',
                source_id='012-6931:A1', nodes=nodes)], 'Controller pin-contract test')
            subprocess.run(['kicad-cli','sch','export','netlist','--format','kicadxml',
                '-o',str(directory/'circuit.xml'),str(sheet)],check=True,capture_output=True)
            inventory = json.loads((ROOT/'reference/k7222-11/inventory.json').read_text())
            result = reference.source_connectivity(directory/'circuit.xml',inventory,
                '012-6931',{'TDA1060_FUNCTIONAL':16})
            self.assertEqual(result[0]['nodes'],nodes)
            self.assertEqual(result[0]['source_id'],'012-6931:A1')

    def test_opt_in_pin_order_and_rejected_extra_pins(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'circuit.xml'
            def netlist(count):
                path.write_text('<export><components><comp ref="X1"><value>CONTROL</value></comp></components><nets>'+''.join(
                    f'<net name="{("0" if i==16 else "p"+str(i))}"><node ref="X1" pin="{i}"/></net>'
                    for i in range(1,count+1))+'</nets></export>')
            netlist(16)
            with self.assertRaises(ValueError):lab.connectivity(path)
            self.assertEqual(lab.connectivity(path,{'CONTROL':16})[0]['nodes'],['p'+str(i) for i in range(1,16)]+['0'])
            netlist(17)
            with self.assertRaises(ValueError):lab.connectivity(path,{'CONTROL':16})
        for contract in [[],{'A':True},{'A':33},{'bad name':16},{'a':2,'A':2}]:
            with self.assertRaises(ValueError):lab.subcircuit_contracts(contract)

    def test_model_declaration_contract(self):
        profile=dict(name='test',probes=[dict(expression='v(a)')],subcircuits={'CONTROL':3})
        for model in ['', '.subckt CONTROL a b\n.ends', '.subckt CONTROL a b c\n.ends\n.subckt CONTROL a b c\n.ends']:
            with self.assertRaises(ValueError):reference.deck(profile,[],{},0,.001,1e-6,model,'')
        self.assertIn('.subckt CONTROL a b c',reference.deck(profile,[],{},0,.001,1e-6,'.subckt CONTROL a b c\n.ends',''))


if __name__ == '__main__':unittest.main()
