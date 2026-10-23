#!/usr/bin/env python3
import json,subprocess,tempfile,unittest
from pathlib import Path
from prepare_boundary_trace import MONITOR,instrument
from live_transition_probe import live_diagnostic as solver_diagnostic
from boundary_transition_review import observations,undefined_intervals

class BoundaryTraceTest(unittest.TestCase):
 def test_native_observer_preserves_unknown_and_ps(self):
  source='''`timescale 1ns/1ps
module test;
reg data_sink=0,clock_sink=0,wr_n=1;
reg [7:0] bus_sense=0;
reg [15:0] address=0;
reg [23:0] bus_low=0,bus_high=0;
'''+MONITOR+'''
initial begin #1.001; data_sink=1'bx;bus_sense=8'bx; #1; $finish; end
endmodule
'''
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'test.v').write_text(source)
   subprocess.run(['iverilog','-g2012','-s','test','-o',str(p/'test.vvp'),str(p/'test.v')],check=True,capture_output=True)
   result=subprocess.check_output(['vvp',str(p/'test.vvp')],text=True)
   self.assertIsNone(solver_diagnostic(result))
   self.assertIn('BOUNDARY_PS 1001 x x 0 1',result)
 def test_undefined_intervals_keep_open_tail(self):
  events=observations('BOUNDARY_PS 10 0 0 1 1 0000 0 0\nBOUNDARY_PS 20 x x 1 1 0000 0 0\nBOUNDARY_PS 30 1 1 1 1 0000 0 0\nBOUNDARY_PS 40 x x 1 1 0000 0 0\n')
  self.assertEqual(undefined_intervals(events,50),[[20,30],[40,50]])
  with self.assertRaises(ValueError):observations('')
 def test_reject_missing_anchor_and_hdl_errors(self):
  with self.assertRaises(ValueError):instrument('unrecognized')
  self.assertIsNotNone(solver_diagnostic('SORRY: currently only simple signals may be passed to $strobe.'))
if __name__=='__main__':unittest.main()
