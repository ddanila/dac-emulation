#!/usr/bin/env python3
"""Reject misleading cache equivalence from equally truncated captures."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess
from eval_cache_benchmark import main
from eval_cache_benchmark import assess,capture_scope,trace_extent

class CaptureTests(unittest.TestCase):
 def test_window_and_corrupt_traces(self):
  scope=capture_scope('.tran 10n 0.002 0\n')
  self.assertEqual(scope['stopSeconds'],.002)
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'trace.txt'
   for body in ('0 0\n.001 5\n','0 0\n.002 nan\n','0 0\n0 1\n.002 5\n','0 0\n.002 5 6\n'):
    p.write_text('time voltage\n'+body)
    with self.assertRaises(ValueError):trace_extent(p,scope)
   p.write_text('')
   with self.assertRaisesRegex(ValueError,'Missing'):trace_extent(p,scope)
   p.write_text('time voltage\n0 0\n.002 5\n')
   self.assertEqual(trace_extent(p,scope)['maximumValue'],5)
 def test_deck_scope(self):
  for deck in ('.tran 1n 2m\n','.tran 0 2m 0\n','.tran 1n 2m 3m\n','.tran 1n 2m 0\n.tran 1n 3m 0\n'):
   with self.assertRaises(ValueError):capture_scope(deck)
 def test_identical_but_incomplete_receipts(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);deck='.tran 10n 0.002 0\n'
   (root/'boot.cir').write_text(deck)
   (root/'scope.json').write_text(json.dumps(capture_scope(deck)))
   for mode in ('off','exact','off-repeat','exact-repeat'):
    folder=root/mode;folder.mkdir();(folder/'ngspice.log').write_text('')
    extent={'samples':2,'firstSeconds':0,'lastSeconds':.001}
    (folder/'run.json').write_text(json.dumps({'mode':mode,'exitCode':0,'elapsedSeconds':1,'sha256':{'trace.txt':'same','supply-trace.txt':'same'},'capture':{'trace.txt':extent,'supply-trace.txt':extent}}))
   with self.assertRaisesRegex(ValueError,'Incomplete'):assess(root)

 def test_timeout_retains_failure_receipt(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);prepared=root/'prepared';prepared.mkdir();out=root/'out'
   for name in ('boot.cir','boot.vvp','s600.hex','ls_nand_nominal.cir'):
    (prepared/name).write_text('.tran 1n 2m 0\n' if name=='boot.cir' else '')
   args=['benchmark','--prepared',str(prepared),'--out',str(out),'--ngspice','fake','--spinit',str(root)]
   with patch('sys.argv',args),patch('eval_cache_benchmark.identify',return_value=({},{})),patch('eval_cache_benchmark.subprocess.run',side_effect=subprocess.TimeoutExpired('fake',1)):
    with self.assertRaisesRegex(ValueError,'timed out'):main()
   receipt=json.loads((out/'off/run.json').read_text())
   self.assertEqual(receipt['exitCode'],-1)
   self.assertIn('timed out',receipt['failure'])
   self.assertTrue((out/'runtime.json').exists())
   self.assertFalse((out/'assessment.json').exists())

if __name__=='__main__':unittest.main()
