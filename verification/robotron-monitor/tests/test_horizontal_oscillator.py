"""Standalone transistor oscillator; no prescribed raster or sync-lock claim."""
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import reference


class HorizontalOscillatorTests(unittest.TestCase):
    def test_autonomous_oscillation_inductance_response_and_refinement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def solve(name,step=1e-6,changes=None):
                out=root/name
                r=reference.run(ROOT/'profiles/k7222-11-horizontal-oscillator.json',out,
                                stop=.005,step=step,changes=changes,runtime=os.environ.get('MONITOR_RUNTIME'))
                rows=reference.read_samples(out/'samples.txt',r['probes'],0,.005,step)
                selected=[v for v in rows if v[0]>.003]
                times=[]
                for a,b in zip(selected,selected[1:]):
                    if a[2]<.3<=b[2]:times.append(a[0]+(b[0]-a[0])*(.3-a[2])/(b[2]-a[2]))
                self.assertGreater(len(times),20)
                period=statistics.median(b-a for a,b in zip(times,times[1:]))
                self.assertGreater(max(v[3] for v in selected)-min(v[3] for v in selected),10)
                self.assertEqual(r['coverage']['connected'],41)
                self.assertFalse(r['coverage']['full_monitor_qualified'])
                self.assertNotIn('PULSE(', (out/'run.cir').read_text())
                self.assertNotIn('SIN(', (out/'run.cir').read_text())
                return period,r
            base,report=solve('base')
            fine,_=solve('fine',step=5e-7)
            slower,_=solve('slower',changes={'horizontal_tank_l':.0018})
            self.assertTrue(1/25000<base<1/15000)
            self.assertLess(abs(base/fine-1),.01)
            self.assertGreater(slower/base,1.15)
            # R15/C8 return must reach feedback THROUGH C17, not through an
            # accidental grounded junction at the crossing on the scan.
            parts={p['source_id']:p for p in report['components']}
            self.assertEqual(parts['012-6921:C17']['nodes'],['h_pdreturn','h_feedback'])
            self.assertEqual(parts['012-6921:R15']['nodes'],['h_control','h_pdreturn'])

    def test_source_table_matches_authored_sheet_export(self):
        import lab
        table=json.loads((ROOT/'reference/k7222-11/horizontal-transcription.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);xml=out/'sheet.xml'
            lab.run_command(['kicad-cli','sch','export','netlist','--format','kicadxml','-o',str(xml),
                             str(ROOT/'circuits/k7222-11-horizontal-oscillator.kicad_sch')],out,out/'export.log')
            inv=json.loads((ROOT/'reference/k7222-11/inventory.json').read_text())
            profile=reference.read_profile(ROOT/'profiles/k7222-11-horizontal-oscillator.json')
            exported=reference.source_connectivity(xml,inv,'012-6921',profile['subcircuits'])
            canonical=lambda parts:sorted((p['source_id'],p['reference'],tuple(p['nodes']),p['value']) for p in parts)
            self.assertEqual(canonical(exported),canonical(table['components']))


if __name__=='__main__':unittest.main()
