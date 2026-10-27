import json,lzma,tempfile,unittest
from pathlib import Path
import parameter_continue_activity as combined
from retained_evidence import check
from memory_board_budget import native_layout
import os
ROOT=Path(os.environ.get('ROBOTRON_PARAMETER_CONTINUE_REPORT',str(Path(__file__).resolve().parent/'reports/parameter-continue-controls')))

@unittest.skipUnless((ROOT/'assessment.json').exists(), 'Complete parameter continuation campaign pending')
class ParameterContinueTests(unittest.TestCase):
    def test_retained_later_faults(self):
        if (ROOT/'manifest.json').exists():check(ROOT)
        r=combined.review(ROOT)
        self.assertEqual(json.loads(json.dumps(r)),json.loads((ROOT/'assessment.json').read_text()))
        self.assertEqual(len(r['negativeControls']),10)
        for value in r['negativeControls'].values():
            self.assertEqual(value['boundaries'],2)
            self.assertGreaterEqual(value['fault']['targetSeconds'],5e-6)
            self.assertGreater(value['fault']['index'],0)
            self.assertEqual(value['scopeMetadata']['memories'],3)
        self.assertTrue(r['firmwareRecordsExactlyEqual'])
        for activity in r['postFaultActivity'].values():
            self.assertEqual(activity['postFaultBusEdges'],4)
            self.assertEqual(activity['lastPostFaultEdgePS'],19501280)
        for comparison in r['completeComparisons'].values():
            self.assertTrue(comparison['allSamplesExactlyEqual'])
            self.assertEqual(comparison['endSeconds'],20e-6)
            self.assertEqual(len(comparison['signals']),31)
    def run_log(self,text,mode='parameter-name-corrupt'):
        run=json.loads((ROOT/mode/'run.json').read_text());ids=combined.preflight.verify_symbols(ROOT,{'off':run});compiled=(ROOT/'baseline/io.vvp').read_text()
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'ngspice.log';p.write_text(text)
            return combined.inventory(p,ids,fault_type=mode.removesuffix('-corrupt'),contract=combined.preflight.port_contract(compiled),compiled=compiled,memory_offset=native_layout(ROOT))
    def test_early_wrong_phase_and_startup_index_reject(self):
        text=lzma.decompress((ROOT/'parameter-name-corrupt/ngspice.log.xz').read_bytes()).decode()
        original=[s for s in text.splitlines() if s.startswith('VB_BRIDGE ')][1];words=original.split()
        for index,value in [(1,'0'),(2,'after-step'),(3,'0.000001')]:
            changed=words.copy();changed[index]=value
            with self.subTest(index=index),self.assertRaises(ValueError):self.run_log(text.replace(original,' '.join(changed),1))
    def test_missing_refusal_or_restoration_reject(self):
        for mode,old,new in [('parameter-scope-corrupt','rejected=1 restored=1','rejected=0 restored=1'),('parameter-name-corrupt','VB_STAGE restored','VB_STAGE changed')]:
            text=lzma.decompress((ROOT/mode/'ngspice.log.xz').read_bytes()).decode();self.assertIn(old,text)
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.run_log(text.replace(old,new,1),mode)

    def test_incomplete_exit_or_summary_reject(self):
        import shutil
        for field in ('exitCode','summary'):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/'parameter-name-corrupt/run.json';r=json.loads(p.read_text())
                if field=='exitCode':r[field]=2
                else:r['summary']['count']-=1
                p.write_text(json.dumps(r))
                with self.assertRaises(ValueError):combined.review(root)

    def test_missing_post_fault_activity_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'ngspice.log';p.write_text('BUS_EDGE_PS 1000000\nBUS_EDGE_PS 5000000\n')
            with self.assertRaisesRegex(ValueError,'Missing post-fault'):combined.activity(p,5e-6)
            p.write_text('BUS_EDGE_PS 7501280\nBUS_EDGE_PS 7501280\n')
            with self.assertRaisesRegex(ValueError,'Invalid bus activity time'):combined.activity(p,5e-6)

class ParameterLateAdmissionTests(unittest.TestCase):
    def test_retained_startup_fault_cannot_prove_later_boundary(self):
        import parameter_fault_review as startup
        import parameter_late_core_review as later
        root=Path(__file__).resolve().parent/'reports/parameter-fault-preflight'
        run=json.loads((root/'parameter-name-corrupt/run.json').read_text())
        identities=startup.preflight.verify_symbols(root,{'off':run})
        compiled=(root/'baseline/io.vvp').read_text()
        original=startup.previous
        try:
            startup.previous=later
            with self.assertRaisesRegex(ValueError,'missed later boundary'):
                startup.inventory(root/'parameter-name-corrupt/ngspice.log',identities,fault_type='parameter-name',contract=later.port_contract(compiled),compiled=compiled)
        finally:startup.previous=original

if __name__=='__main__':unittest.main()
