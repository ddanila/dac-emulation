#!/usr/bin/env python3
"""Electrical control receivers must supersede ideal pullups and driver intent."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from controller_interface import generate, HERE


class LogicInterfaceTests(unittest.TestCase):
    def test_physical_receivers_drive_latch_and_flip_flops(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            (out / 'controller_analog.v').write_text(generate(explicit_cpu_drive=True, resolved_bus=True))
            (out / 'tb.v').write_text('''`timescale 1ns/1ps
module tb;
 reg [15:0] address=16'hc000;
 reg iorq_n=1;
 reg [2:0] levels=3'b011;
 reg [7:0] sense=8'ha5;
 wire [1:0] sinks;
 wire [7:0] data;
 controller_analog #(.ELECTRICAL_LOGIC_PULLUPS(1)) dut(
  .address(address),.cpu_data(8'b0),.cpu_drive(1'b0),.iorq_n(iorq_n),.wr_n(1'b1),
  .mreq_n(1'b1),.rom_data(8'b0),.sense(sense),.logic_control(levels),.logic_sink(sinks),.read_data(data));
 controller_analog legacy(
  .address(address),.cpu_data(8'b0),.cpu_drive(1'b0),.iorq_n(iorq_n),.wr_n(1'b1),
  .mreq_n(1'b1),.rom_data(8'b0),.sense(sense),.logic_control(3'bxxx));
 initial begin
  #1;
  if(sinks!==2'b11 || dut.A4.p9!==1 || dut.A4.p11!==0 || dut.A6.p1!==1)
   $fatal(1,"Driver/receiver boundary lost or vector reversed");
  if(legacy.A4.p9!==0 || legacy.A4.p11!==0 || legacy.A6.p1!==1)
   $fatal(1,"Legacy pullup/collector behavior changed");
  levels=3'b110; #1;
  if(data!==8'ha5 || dut.A6.p3!==1 || dut.A6.p11!==1)
   $fatal(1,"Returned strobe did not reach latch and both flip-flop clocks");
  levels=3'b010; sense=8'h3c; #1;
  if(data!==8'ha5) $fatal(1,"Latch failed to hold at returned low");
  iorq_n=0; #1;
  if(sinks!==2'b01 || data!==8'ha5 || dut.A4.p11!==0)
   $fatal(1,"Driver intent bypassed physical feedback");
  levels=3'b110; #1;
  if(data!==8'h3c) $fatal(1,"Delayed return did not make latch transparent");
  levels=3'b000; #1;
  if(dut.A6.p6!==1 || dut.A6.p8!==1)
   $fatal(1,"Returned async controls did not reach both flip-flops");
  levels=3'bxxx; #1;
  if(dut.A4.p9!==1'bx || dut.A4.p11!==1'bx || dut.A6.p1!==1'bx)
   $fatal(1,"Ideal pullup masked unknown receiver state");
  $display("LOGIC_INTERFACE_OK"); $finish;
 end
endmodule
''')
            subprocess.run(['iverilog', '-g2012', '-s', 'tb', '-o', str(out / 'tb.vvp'),
                            str(HERE.parent / 'chips.v'), str(out / 'controller_analog.v'), str(out / 'tb.v')],
                           check=True, capture_output=True, text=True)
            result = subprocess.run(['vvp', str(out / 'tb.vvp')], check=True, capture_output=True, text=True)
            self.assertIn('LOGIC_INTERFACE_OK', result.stdout)


if __name__ == '__main__':
    unittest.main()
