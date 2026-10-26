import unittest
from output_breakpoint_review import branches

def record(phase=0,status=0,inject=0,when='0x1.1p+1'):
    return f'OUTPUT_BKPT recovery={phase} time=0x1p+3 vtime=0x1p+1 requested={when} last=0x1p+0 status={status} injected={inject}'

class BranchTests(unittest.TestCase):
    def test_coverage_requires_real_branch_and_injection(self):
        self.assertFalse(branches([],'fail-once')['injectionExercised'])
        self.assertFalse(branches([],'observe')['branchExercised'])
        r=branches([record(status=1,inject=1),record(phase=1),record()],'fail-once')
        self.assertEqual((r['initialRequests'],r['recoveryRequests'],r['injectedFailures']),(2,1,1))

    def test_bad_sequence_cannot_claim_recovery(self):
        cases=[[record(phase=1)],[record(status=1)],
               [record(status=1,inject=1),record(phase=1),record(status=1,inject=1),record(phase=1)],
               [record(status=1),record(phase=1,status=1),record(phase=1,when='0x1p+1')],
               [record(when='nan')],[record(inject=1)],['OUTPUT_BKPT incomplete']]
        for lines in cases:
            with self.subTest(lines=lines),self.assertRaises(ValueError):branches(lines,'fail-once')
        for mode in ('off','observe'):
            with self.assertRaises(ValueError):branches([record(status=1,inject=1),record(phase=1)],mode)

if __name__=='__main__':unittest.main()
