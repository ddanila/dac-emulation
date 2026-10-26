import json
from pathlib import Path
import unittest
from build_private_sync_bridge import instrument

HERE=Path(__file__).resolve().parent


class PrivateSyncBridgeTests(unittest.TestCase):
    def setUp(self):
        source=json.loads((HERE/'reports/barrier-state-source/assessment.json').read_text())
        self.step=source['sourceExcerpts']['src/xspice/verilog/icarus_shim.c']['excerpt']
        self.header=(HERE/'fixtures/private_sync_bridge.h').read_text()

    def test_only_brackets_the_mutex_release_and_reacquisition(self):
        candidate=instrument(self.step,self.header)
        before='    private_sync_boundary(pinfo, "before-step");\n'
        after='    private_sync_boundary(pinfo, "after-step");\n'
        self.assertEqual(candidate.count(before),1)
        self.assertEqual(candidate.count(after),1)
        self.assertIn(before+'    cr_yield_to_sim(&ctx->cr_ctx);\n'+after,candidate)
        self.assertEqual(candidate.replace(self.header+'\n','',1).replace(before,'',1).replace(after,'',1),self.step)

    def test_changed_or_ambiguous_bridge_boundary_rejected(self):
        for source in (self.step+self.step,self.step.replace('cr_yield_to_sim','other_yield')):
            with self.assertRaises(ValueError):instrument(source,self.header)


if __name__=='__main__':unittest.main()
