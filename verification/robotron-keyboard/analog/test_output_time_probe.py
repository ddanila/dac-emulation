"""Distinguish autonomous settling from required input-causality clamping."""
import json,shutil,tempfile,unittest
from pathlib import Path
import output_time_probe as probe
import build_output_drain_vpi as builder
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
ROOT=HERE/'reports/output-drain'

class OutputTimeTests(unittest.TestCase):
    def test_native_controls(self):
        result=probe.review(ROOT)
        self.assertEqual(result,json.loads((ROOT/'assessment.json').read_text()))
        self.assertTrue(result['delayedAutonomousCases'])
        self.assertTrue(result['clampedInputCases'])
        self.assertTrue(result['drainedAutonomousTimesExactlyMatchNative'])

    def test_no_backward_output(self):
        text='RETURN requested=0x1p+0 returned=0x1p+0\nOUTPUT_TICK 1\nOUTPUT time=0x1p-1 bit=0 state=1 strength=0\n'
        with self.assertRaisesRegex(ValueError,'precedes'):probe.observe(text)

    def test_delayed_autonomous_edge_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for p in ROOT.iterdir():
                if p.suffix=='.log' or p.name=='run.json':shutil.copy2(p,root/p.name)
            receipt=json.loads((root/'run.json').read_text());entry=receipt['runs']['10000-quarter-direct-0/drain'];p=root/entry['log'];s=p.read_text()
            import re
            s=re.sub(r'OUTPUT time=\S+ bit=0 state=1',f"OUTPUT time={entry['target']} bit=0 state=1",s);p.write_text(s);entry['sha256']=sha(p)
            (root/'run.json').write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError,'autonomous event time'):probe.review(root)

    def test_clamp_preserved_and_source_boundary_guarded(self):
        source=(HERE/'reports/postreset-tick/candidate-vpi.c').read_text();candidate=builder.instrument(source)
        clamp='''        if (ctx->cosim_context->vtime < ctx->base_time)
            ctx->cosim_context->vtime = ctx->base_time;'''
        self.assertEqual(source.count(clamp),1);self.assertEqual(candidate.count(clamp),1)
        with self.assertRaisesRegex(ValueError,'boundary'):builder.instrument(source.replace('now.low = (unsigned int)length;','now.low = 0;'))

    def test_board_conditions_isolate_tick_and_drain(self):
        from output_drain_board_review import conditions
        self.assertEqual(conditions({},'off'),{})
        self.assertEqual(conditions({},'tick'),{'ROBOTRON_ABSOLUTE_TICKS':'1'})
        self.assertEqual(conditions({},'on'),{'ROBOTRON_ABSOLUTE_TICKS':'1','ROBOTRON_DRAIN_TICK':'1'})
        self.assertEqual(conditions({},'retry')['ROBOTRON_FORCE_NEWTON_REJECT'],'1')

if __name__=='__main__':unittest.main()
