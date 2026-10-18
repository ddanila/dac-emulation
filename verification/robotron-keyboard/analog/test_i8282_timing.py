#!/usr/bin/env python3
"""Exercise Intel 8282 storage constraints and output timing uncertainty."""
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class LatchTimingTests(unittest.TestCase):
    def test_storage_hold_pulse_and_output_envelopes(self):
        bench = '''`timescale 1ns/1ps
module tb;
 reg [7:0] data=8'ha5;
 reg stb=0,oe_n=1;
 wire [7:0] q,constant_q;
 chip_I8282_timed fixed_inputs(.p1(1'b1),.p2(1'b0),.p3(1'b1),.p4(1'b0),
 .p5(1'b0),.p6(1'b1),.p7(1'b0),.p8(1'b1),.p9(1'b0),.p10(1'b0),
 .p11(1'b1),.p20(1'b1),.p19(constant_q[0]),.p18(constant_q[1]),
 .p17(constant_q[2]),.p16(constant_q[3]),.p15(constant_q[4]),
 .p14(constant_q[5]),.p13(constant_q[6]),.p12(constant_q[7]));
 chip_I8282_timed dut(.p1(data[0]),.p2(data[1]),.p3(data[2]),.p4(data[3]),
 .p5(data[4]),.p6(data[5]),.p7(data[6]),.p8(data[7]),.p9(oe_n),.p10(1'b0),
 .p11(stb),.p20(1'b1),.p19(q[0]),.p18(q[1]),.p17(q[2]),.p16(q[3]),
 .p15(q[4]),.p14(q[5]),.p13(q[6]),.p12(q[7]));
 task expected(input [7:0] value);
  if(q!==value)$fatal(1,"At %t expected %b, got %b",$time,value,q);
 endtask
 initial begin
  #60;expected(8'hzz);
  if(constant_q!==8'ha5)$fatal(1,"Constant transparent inputs did not settle");
  stb=1;oe_n=0;
  #49;expected(8'hxx);
  #5;expected(8'hxx);
  #2;expected(8'ha5);
  data=8'h5a;#34;expected(8'hxx);#2;expected(8'h5a);
  stb=0;#56;expected(8'h5a);
  data=8'hff;#50;expected(8'h5a); // Closed latch ignores later input.
  stb=1;#60;stb=0;#24;data=8'hfe;#40;
  expected(8'b1111111x); // Hold violation poisons only the changed bit.
  stb=1;#60;stb=0;#25;data=8'hfc;#40;
  expected(8'hfe); // At the minimum hold interval the previous data is retained.
  data=8'h3c;stb=1;#14;stb=0;#60;expected(8'hxx);
  stb=1;#15;stb=0;#60;expected(8'h3c);
  oe_n=1;#24;expected(8'hxx);#2;expected(8'hzz);
  oe_n=0;#49;expected(8'hxx);#2;expected(8'h3c);
  data=8'h3d;stb=1'bx;#60;expected(8'b0011110x);
  stb=0;#60;expected(8'b0011110x);
  stb=1;#60;expected(8'h3d); // Valid transparency recovers storage certainty.
  oe_n=1'bx;#60;expected(8'hxx);
  oe_n=1;#26;expected(8'hzz);
  $display("LATCH_TIMING_PASS");$finish;
 end
endmodule
'''
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / 'tb.v').write_text(bench)
            subprocess.run(['iverilog', '-g2012', '-s', 'tb', '-o', str(out / 'test.vvp'),
                            str(HERE / 'i8282_timing.v'), str(out / 'tb.v')], check=True)
            result = subprocess.run(['vvp', str(out / 'test.vvp')], capture_output=True,
                                    text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('LATCH_TIMING_PASS', result.stdout)


if __name__ == '__main__':
    unittest.main()
