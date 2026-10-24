import unittest
from bridge_rollback_log import analyze


def client(phase,time):
    return f'ROLLBACK_AUDIT client phase={phase} time={float(time).hex()} name=hdl priority=1 index=0 count=1 breakpoint=0x1p+10'


def sequence(actual=.5):
    return ['ROLLBACK_AUDIT accept time=0x0p+0',client('before',2),
            'TIME_AUDIT advance target=2 actual=0 base=0 tick=.1 pending=0',
            'TIME_AUDIT output actual=.5 target=2 base=0 port=clock',client('after',2),
            'ROLLBACK_AUDIT reject kind=breakpoint time=0x1p+1 delta=0x1p+1 target=0x1p+0',
            client('before',1),f'TIME_AUDIT advance target=1 actual={actual} base=.5 tick=.1 pending=0',
            client('after',1),'ROLLBACK_AUDIT accept time=0x1p+0']


class BridgeRollbackLogTests(unittest.TestCase):
    def test_decreasing_target_after_early_output_is_not_time_reversal(self):
        result=analyze(sequence())
        self.assertTrue(result['timeOrderScreenPassed'])
        self.assertEqual(result['decreasingRequestedTargets'],1)
        self.assertEqual(result['callbacksBeforeRejectionWithAdvanceRequests'],{'breakpoint':1})

    def test_detects_request_before_actual_hdl_and_backward_observation(self):
        result=analyze(sequence(1.5))
        self.assertFalse(result['timeOrderScreenPassed'])
        self.assertEqual(result['requestsEarlierThanActualByMoreThanOneTick'],1)
        self.assertFalse(analyze(sequence(.25))['timeOrderScreenPassed'])

    def test_barrier_callback_without_advance_is_kept_separate(self):
        lines=sequence()
        lines=[line for i,line in enumerate(lines) if i not in (2,3)]
        result=analyze(lines)
        self.assertEqual(result['callbacksBeforeRejectionWithoutAdvanceRequests'],{'breakpoint':1})
        self.assertEqual(result['callbacksBeforeRejectionWithAdvanceRequests'],{})
        self.assertFalse(result['qualified'])

    def test_rejects_orphan_incomplete_and_malformed_records(self):
        for lines in (sequence()[:-2],['TIME_AUDIT advance target=1 actual=0 base=0 tick=.1 pending=0'],
                      sequence()+['TIME_AUDIT advance target=nan']):
            with self.subTest(lines=lines),self.assertRaises(ValueError):analyze(lines)

    def test_terminal_observation_requires_declared_endpoint_and_no_advance(self):
        terminal='TIME_AUDIT advance target=1 actual=1 base=1 tick=.1 pending=0'
        result=analyze(sequence()+[terminal],expected_end=1)
        self.assertEqual(result['terminalBridgeObservation']['actual'],1)
        for lines,end in ((sequence()+[terminal],None), (sequence()+[terminal],2),
                          (sequence()+[terminal.replace('actual=1','actual=.9')],1),
                          (sequence()+[terminal.replace('pending=0','pending=1')],1),
                          (sequence()+[terminal,terminal],1),
                          (sequence()+[terminal,client('before',2)],1)):
            with self.subTest(lines=lines,end=end),self.assertRaises(ValueError):
                analyze(lines,expected_end=end)


if __name__=='__main__':unittest.main()
