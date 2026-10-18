#!/usr/bin/env python3
"""Execute reference ROM access windows and schematic-wired drive intent."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from electrical_bus_interface import generate, generate_service
from cpu_read_phase_candidate import circuit_sources

HERE = Path(__file__).resolve().parent


class EpromTimingTests(unittest.TestCase):
    def run_hdl(self, bench, generated=False):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / 'tb.v').write_text('`timescale 1ns/1ps\n' + bench)
            (out / 'model.v').write_text(generate(rom_timing=True) if generated else
                                         (HERE / 'eprom2716.v').read_text())
            subprocess.run(['iverilog', '-g2012', '-s', 'tb', '-o', str(out / 'test.vvp'),
                            str(out / 'model.v'), str(HERE.parent / 'chips.v'),
                            str(out / 'tb.v')], check=True)
            result = subprocess.run(['vvp', str(out / 'test.vvp')], check=False,
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('ROM_TIMING_PASS', result.stdout)

    def test_cpu_executes_program_through_timed_rom_bus(self):
        for profile in ('tv80', 'falling-indexed-candidate'):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as directory:
                out = Path(directory)
                (out / 'model.v').write_text(generate_service(cpu_profile=profile, rom_timing=True, latch_timing=True))
                program = bytes([0x3e, 0x80, 0xdb, 0x80, 0xd3, 0x80, 0x76]) + bytes([0x76]) * 2041
                (out / 's600.hex').write_text(''.join(f'{b:02x}\n' for b in program))
                (out / 'tb.v').write_text("""`timescale 1ns/1ps
module tb;
 reg clk=0,reset_n=0;
 tri1 [7:0] bus;
 wire [23:0] lo,hi;
 firmware_io_electrical_bus dut(.fixture_clk(clk),.fixture_reset_n(reset_n),
  .sense(8'hff),.receiver_data(1'b0),.receiver_clock(1'b0),
  .bus_sense(bus),.bus_low(lo),.bus_high(hi));
 genvar i;
 generate for(i=0;i<24;i=i+1) begin: drivers
  assign bus[i%8]=lo[i]===1'b0 && hi[i]===1'b0 ? 1'bz :
                 lo[i]===1'b1 && hi[i]===1'b0 ? 1'b0 :
                 lo[i]===1'b0 && hi[i]===1'b1 ? 1'b1 : 1'bx;
 end endgenerate
 always #500 clk=~clk;
 initial begin #2200;reset_n=1;#50000;$fatal(1,"Missing ROM program output");end
 always @(negedge dut.board.wr_n) if(reset_n && !dut.board.iorq_n) begin
  if(dut.board.dout!==8'hff)$fatal(1,"Timed ROM/latch input lost");
  $display("ROM_TIMING_CPU_PASS");$finish;
 end
endmodule
""")
                sources, _ = circuit_sources(HERE.parents[2] / 'third_party/cpu/tv80', out, profile)
                subprocess.run(['iverilog', '-g2012', '-s', 'tb', '-o', str(out / 'run.vvp'),
                                *map(str, sources), str(out / 'model.v'),
                                str(HERE.parent / 'chips.v'), str(HERE.parent / 'generated/controller.v'),
                                str(out / 'tb.v')], check=True)
                result = subprocess.run(['vvp', 'run.vvp'], cwd=out, capture_output=True,
                                        text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('ROM_TIMING_CPU_PASS', result.stdout)

    def test_access_release_glitches_and_unknown_controls(self):
        self.run_hdl('''module tb;
 reg [10:0] address=0;
 reg ce_n=1,oe_n=1;
 wire [7:0] q;
 wire [7:0] data=address==0 ? 8'ha5 : 8'h3c;
 eprom2716_read_envelope dut(address,data,ce_n,oe_n,q);
 task expect_x; if(q!==8'hxx)$fatal(1,"Expected unspecified data at %t: %h",$time,q); endtask
 task expect_z; if(q!==8'hzz)$fatal(1,"Expected release at %t: %h",$time,q); endtask
 initial begin
  #101;expect_z;
  ce_n=0;oe_n=0;
  #121;expect_x; // OE ready, CE still pending.
  #328;expect_x;
  #2;if(q!==8'ha5)$fatal(1,"CE access deadline");
  address=1;
  #449;expect_x;
  #2;if(q!==8'h3c)$fatal(1,"Address access deadline");
  address=0;#100;address=1;
  #351;expect_x; // Stale completion for address 0 must not validate address 1.
  #100;if(q!==8'h3c)$fatal(1,"Repeated address recovery");
  oe_n=1;#99;expect_x;
  #2;expect_z;
  oe_n=0;#119;expect_x;
  #2;if(q!==8'h3c)$fatal(1,"OE access deadline");
  oe_n=1;#30;oe_n=0;#89;expect_x;
  #32;if(q!==8'h3c)$fatal(1,"Short OE pulse recovery");
  oe_n=1;#101;ce_n=1'bx;#1;expect_z;
  oe_n=0;#500;expect_x;
  ce_n=0;address=11'bxxxxxxxxxxx;#500;expect_x;
  address=0;#451;if(q!==8'ha5)$fatal(1,"Unknown address recovery");
  ce_n=1;#50;oe_n=1;#51;expect_z; // First disable starts tDF.
  $display("ROM_TIMING_PASS");$finish;
 end
endmodule''')

    def test_schematic_rom_oe_and_address_control_electrical_driver(self):
        self.run_hdl('''module tb;
 reg [15:0] address=0;
 reg mreq_n=1;
 wire [23:0] lo,hi;
 controller_electrical_bus dut(.address(address),.cpu_data(8'h00),.cpu_drive(1'b0),
 .iorq_n(1'b1),.wr_n(1'b1),.mreq_n(mreq_n),.rom_data(8'ha5),
 .sense(8'hff),.bus_sense(8'h00),.bus_low(lo),.bus_high(hi));
 initial begin
  #501;if({lo[15:8],hi[15:8]}!==16'h0000)$fatal(1,"ROM must release");
  mreq_n=0;#119;
  if({lo[15:8],hi[15:8]}!==16'hxxxx)$fatal(1,"OE access uncertainty lost");
  #2;if({lo[15:8],hi[15:8]}!==16'h5aa5)$fatal(1,"Schematic OE deadline");
  address=1;#449;
  if({lo[15:8],hi[15:8]}!==16'hxxxx)$fatal(1,"Address uncertainty lost");
  #2;if({lo[15:8],hi[15:8]}!==16'h5aa5)$fatal(1,"Address deadline");
  mreq_n=1;#99;
  if({lo[15:8],hi[15:8]}!==16'hxxxx)$fatal(1,"Release uncertainty lost");
  #2;if({lo[15:8],hi[15:8]}!==16'h0000)$fatal(1,"Release deadline");
  $display("ROM_TIMING_PASS");$finish;
 end
endmodule''', generated=True)


if __name__ == '__main__':
    unittest.main()
