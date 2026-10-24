#!/usr/bin/env python3
import copy
import tempfile
import unittest
from pathlib import Path
from reset_release_driver_review import completed,trace_summary,TRACES

class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.run={'timedOut':False,'exitCode':0,'stopNs':1002000}
        self.traces={name:{'samples':2,'firstSeconds':0,'lastSeconds':.001002,'strictlyIncreasing':True} for name in TRACES}

    def test_success_requires_every_complete_trace(self):
        self.assertTrue(completed(self.run,self.traces,None))
        self.traces.pop('bus-trace.txt')
        self.assertFalse(completed(self.run,self.traces,None))

    def test_zero_exit_abort_or_truncation_never_passes(self):
        self.assertFalse(completed(self.run,self.traces,'run simulation(s) aborted'))
        self.traces['witness.txt']['lastSeconds']=.001001012
        self.assertFalse(completed(self.run,self.traces,None))

    def test_timeout_and_nonmonotonic_trace_never_pass(self):
        run=copy.deepcopy(self.run);run['timedOut']=True
        self.assertFalse(completed(run,self.traces,None))
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'trace.txt';p.write_text('time v(a)\n0 0\n0.001002 1\n0.001002 2\n')
            record=trace_summary(p)
            self.assertFalse(record['strictlyIncreasing'])
            self.assertEqual(len(record['tail']),3)
            self.traces['witness.txt']=record
            self.assertFalse(completed(self.run,self.traces,None))

if __name__=='__main__':unittest.main()
