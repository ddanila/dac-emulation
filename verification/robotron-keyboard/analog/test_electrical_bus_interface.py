#!/usr/bin/env python3
"""Check independent drive intent and voltage-derived reads with the real chip HDL."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from electrical_bus_interface import generate, generate_service

HERE = Path(__file__).resolve().parent


class ElectricalBusInterfaceTests(unittest.TestCase):
    def test_service_cpu_reads_returned_voltage_logic(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / 'controller.v').write_text(generate_service())
            (out / 's600.hex').write_text('a5\n' * 2048)
            (out / 'tb.v').write_text('''`timescale 1ns/1ps
module tb;
 reg [7:0] sense=8'h3c;
 wire [23:0] lo,hi;
 firmware_io_electrical_bus dut(.fixture_clk(1'b0),.fixture_reset_n(1'b1),
 .sense(8'hff),.receiver_data(1'b0),.receiver_clock(1'b0),
 .bus_sense(sense),.bus_low(lo),.bus_high(hi));
 initial begin
  force dut.board.address=0;
  force dut.board.mreq_n=0;
  force dut.board.iorq_n=1;
  force dut.board.cpu_data_drive=0;
  #1;
  if(dut.board.cpu.di!==8'h3c || hi[15:8]!==8'ha5 || lo[15:8]!==8'h5a)
   $fatal(1,"CPU must read sensed bus independently of ROM drive");
  sense=8'bxxxxxxxx; #1;
  if(dut.board.cpu.di!==8'bxxxxxxxx)$fatal(1,"CPU unknown receiver masked");
  force dut.board.cpu_data_drive=1;
  force dut.board.dout=8'h5a;
  sense=0; #1;
  if(hi[7:0]!==8'h5a || lo[7:0]!==8'ha5 || hi[15:8]!==8'ha5 ||
     dut.board.cpu.di!==0)$fatal(1,"CPU/ROM drive or sensed contention lost");
  $display("SERVICE_BUS_PASS");$finish;
 end
endmodule
''')
            tv80 = HERE.parents[2] / 'third_party/cpu/tv80'
            subprocess.run(['iverilog', '-g2012', '-s', 'tb', '-o', str(out / 'bus.vvp'),
                            *map(str, sorted(tv80.glob('*.v'))), str(out / 'controller.v'),
                            str(HERE.parent / 'chips.v'), str(HERE.parent / 'generated/controller.v'),
                            str(out / 'tb.v')], check=True)
            result = subprocess.run(['vvp', str(out / 'bus.vvp')], cwd=out,
                                    capture_output=True, text=True, check=True, timeout=30)
            self.assertIn('SERVICE_BUS_PASS', result.stdout)

    def test_wr_reset_bus_handover_and_unknown_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / 'controller.v').write_text(generate_service(electrical_wr=True))
            (out / 's600.hex').write_text('00\n' * 2048)
            (out / 'tb.v').write_text("""`timescale 1ns/1ps
module tb;
 reg reset_n=0;
 wire lo,hi;
 firmware_io_electrical_bus dut(.fixture_clk(1'b0),.fixture_reset_n(reset_n),
 .sense(8'hff),.receiver_data(1'b0),.receiver_clock(1'b0),
 .bus_sense(8'h00),.wr_low(lo),.wr_high(hi));
 initial begin
  force dut.board.busak_n=1'bx; force dut.board.wr_n=1'bx;
  #1;if({lo,hi}!==2'b01)$fatal(1,"Reset must make WR inactive, not float");
  reset_n=1;force dut.board.busak_n=1;force dut.board.wr_n=0;
  #1;if({lo,hi}!==2'b10)$fatal(1,"WR assertion lost");
  force dut.board.wr_n=1;
  #1;if({lo,hi}!==2'b01)$fatal(1,"WR deassertion lost");
  force dut.board.busak_n=0;force dut.board.wr_n=1'bx;
  #1;if({lo,hi}!==2'b00)$fatal(1,"BUSACK must release both WR drivers");
  force dut.board.busak_n=1;
  #1;if({lo,hi}!==2'bxx)$fatal(1,"Unknown WR masked");
  force dut.board.busak_n=1'bx;force dut.board.wr_n=1;
  #1;if({lo,hi}!==2'bxx)$fatal(1,"Unknown ownership masked");
  reset_n=1'bx;
  #1;if({lo,hi}!==2'bxx)$fatal(1,"Unknown reset masked");
  reset_n=0;
  #1;if({lo,hi}!==2'b01)$fatal(1,"Reset recovery failed");
  $display("WR_OWNERSHIP_PASS");$finish;
 end
endmodule
""")
            tv80 = HERE.parents[2] / 'third_party/cpu/tv80'
            subprocess.run(['iverilog', '-g2012', '-s', 'tb', '-o', str(out / 'wr.vvp'),
                            *map(str, sorted(tv80.glob('*.v'))), str(out / 'controller.v'),
                            str(HERE.parent / 'chips.v'), str(HERE.parent / 'generated/controller.v'),
                            str(out / 'tb.v')], check=True)
            result = subprocess.run(['vvp', str(out / 'wr.vvp')], cwd=out,
                                    capture_output=True, text=True, check=True, timeout=30)
            self.assertIn('WR_OWNERSHIP_PASS', result.stdout)

    def test_independent_drivers_and_receiver_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / 'controller.v').write_text(generate())
            subprocess.run(['iverilog', '-g2012', '-s', 'electrical_bus_tb',
                            '-o', str(out / 'bus.vvp'), str(out / 'controller.v'),
                            str(HERE.parent / 'chips.v'), str(HERE / 'electrical_bus_tb.v')], check=True)
            result = subprocess.run(['vvp', str(out / 'bus.vvp')],
                                    capture_output=True, text=True, check=True, timeout=30)
            self.assertIn('ELECTRICAL_BUS_INTERFACE_PASS', result.stdout)


if __name__ == '__main__':
    unittest.main()
