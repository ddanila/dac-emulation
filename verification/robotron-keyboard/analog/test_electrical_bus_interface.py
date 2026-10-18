#!/usr/bin/env python3
"""Check independent drive intent and voltage-derived reads with the real chip HDL."""
from pathlib import Path
import subprocess
import tempfile
import unittest
import re

from electrical_bus_interface import generate, generate_service
from cpu_read_phase_candidate import circuit_sources

HERE = Path(__file__).resolve().parent


class ElectricalBusInterfaceTests(unittest.TestCase):
    def test_host_receiver_polarity_and_unknown_data(self):
        for host in (0, 1):
            with self.subTest(host=host), tempfile.TemporaryDirectory() as directory:
                out = Path(directory)
                (out / 'controller.v').write_text(generate_service())
                (out / 's600.hex').write_text('00\n' * 2048)
                (out / 'probe.v').write_text(f"""`timescale 1ns/1ps
module probe;
 reg rxclock=0,rxdata={host};
 firmware_io_electrical_bus #(.HOST_BUFFER({host})) dut(
 .fixture_clk(1'b0),.fixture_reset_n(1'b1),.sense(8'hff),
 .receiver_data(rxdata),.receiver_clock(rxclock),.bus_sense(8'h00));
 initial begin
  #10;rxclock=1;
  #5;rxdata={1-host}; #5;rxclock=0;
  #10;rxclock=1;
  #5;rxdata=1'bx; #5;rxclock=0;
  #10;rxclock=1;
  #1;$finish;
 end
endmodule
""")
                sources, _ = circuit_sources(HERE.parents[2] / 'third_party/cpu/tv80', out, 'tv80')
                subprocess.run(['iverilog', '-g2012', '-s', 'probe', '-o', str(out/'probe.vvp'),
                                *map(str,sources), str(out/'controller.v'), str(HERE.parent/'chips.v'),
                                str(HERE.parent/'generated/controller.v'), str(out/'probe.v')], check=True)
                result = subprocess.run(['vvp','probe.vvp'],cwd=out,capture_output=True,text=True,check=True,timeout=30)
                events = re.findall(r'^SERIAL_RX (\d+) ([01x])$',result.stdout,re.M)
                self.assertEqual(events,[('10000','1'),('30000','0'),('50000','x')])

    def test_host_transmit_intent_uses_clock_assertion(self):
        for host, expected in ((0, [('30000','1'),('50000','0')]),
                               (1, [('20000','1'),('40000','0')])):
            with self.subTest(host=host), tempfile.TemporaryDirectory() as directory:
                out=Path(directory)
                (out/'controller.v').write_text(generate_service())
                (out/'s600.hex').write_text('00\n'*2048)
                (out/'probe.v').write_text(f"""`timescale 1ns/1ps
module probe;
 reg reset_n=0;
 firmware_io_electrical_bus #(.HOST_BUFFER({host})) dut(
 .fixture_clk(1'b0),.fixture_reset_n(reset_n),.sense(8'hff),
 .receiver_data(1'b0),.receiver_clock(1'b0),.bus_sense(8'h00));
 initial begin
  force dut.board.ta_takt=1'b1; force dut.board.ta_daten=1'b0;
  #10;reset_n=1;
  #10;force dut.board.ta_takt=1'b0;
  #10;force dut.board.ta_takt=1'b1;
  #5;force dut.board.ta_daten=1'b1;
  #5;force dut.board.ta_takt=1'b0;
  #10;force dut.board.ta_takt=1'b1;
  #1;$finish;
 end
endmodule
""")
                sources,_=circuit_sources(HERE.parents[2]/'third_party/cpu/tv80',out,'tv80')
                subprocess.run(['iverilog','-g2012','-s','probe','-o',str(out/'probe.vvp'),
                    *map(str,sources),str(out/'controller.v'),str(HERE.parent/'chips.v'),
                    str(HERE.parent/'generated/controller.v'),str(out/'probe.v')],check=True)
                result=subprocess.run(['vvp','probe.vvp'],cwd=out,capture_output=True,text=True,check=True,timeout=30)
                self.assertEqual(re.findall(r'^SERIAL_TX (\d+) ([01x])$',result.stdout,re.M),expected)

    def test_observer_follows_selected_cpu_sampling_edge(self):
        for profile, expected, stamp in (('tv80', '12', '8500000'),
                                         ('falling-indexed-candidate', '34', '9000000')):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as directory:
                out = Path(directory)
                (out / 'controller.v').write_text(generate_service(cpu_profile=profile))
                (out / 's600.hex').write_text('00\n' * 2048)
                bench = """`timescale 1ns/1ps
module probe;
 reg clk=0,reset_n=0,late=0;
 wire [15:0] address=dut.board.address;
 wire [7:0] dout=dut.board.dout;
 wire [7:0] di=address==0 ? 8'h3e : address==1 ? (late?8'h34:8'h12) :
               address==2 ? 8'hd3 : address==3 ? 8'h80 : 8'h76;
 firmware_io_electrical_bus dut(.fixture_clk(clk),.fixture_reset_n(reset_n),
 .sense(8'hff),.receiver_data(1'b0),.receiver_clock(1'b0),.bus_sense(di));
 always #500 clk=~clk;
 initial begin #2200;reset_n=1;#50000;$fatal(1,"Missing instruction output");end
 always @(posedge clk) if(reset_n && dut.board.cpu.tstate[2] &&
     !dut.board.cpu.mcycle[0] && !dut.board.mreq_n && !dut.board.rd_n && address==1)
   #100 late=1;
 always @(negedge dut.board.wr_n) if(reset_n && !dut.board.iorq_n) begin
   if(dout!==8'hEXPECTED)$fatal(1,"Wrong instruction operand");
   $display("CIRCUIT_CPU_PHASE_PASS");$finish;
 end
endmodule
""".replace('EXPECTED', expected)
                (out / 'probe.v').write_text(bench)
                sources, model = circuit_sources(HERE.parents[2] / 'third_party/cpu/tv80', out, profile)
                self.assertEqual(model['profile'], profile)
                subprocess.run(['iverilog', '-g2012', '-s', 'probe', '-o', str(out / 'probe.vvp'),
                                *map(str, sources), str(out / 'controller.v'),
                                str(HERE.parent / 'chips.v'), str(HERE.parent / 'generated/controller.v'),
                                str(out / 'probe.v')], check=True)
                result = subprocess.run(['vvp', 'probe.vvp'], cwd=out, capture_output=True,
                                        text=True, check=True, timeout=30)
                self.assertIn('CIRCUIT_CPU_PHASE_PASS', result.stdout)
                reads = re.findall(r'^BUS_SAMPLE (\d+) 0001 ([0-9a-f]{2}) 0 1 1$', result.stdout, re.M)
                self.assertEqual(reads, [(stamp, expected)])
                self.assertIn('BUS_LATCH ' + stamp + ' ' + expected + ' ' + expected, result.stdout)
                self.assertIn('BUS_SAMPLE 4500000 0000 3e 0 1 0', result.stdout)

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
  force dut.board.reset_n=1;
  force dut.board.cpu.tstate=7'b0000100;
  force dut.board.cpu.wait_n=1;
  force dut.board.rd_n=0;
  force dut.board.m1_n=1;
  force dut.board.clk=0;
  #1; force dut.board.clk=1;
  // End before any following falling edge: the completed latch still exists.
  #0.1;
  force dut.board.cpu_data_drive=0;
  force dut.board.mreq_n=1; force dut.board.iorq_n=0;
  #1;
  if(lo!==24'h000000 || hi!==24'h000000)
   $fatal(1,"A15-low I/O read must release CPU, ROM and latch drivers");
  force dut.board.address=16'h8000;
  #1;
  if(lo!==24'h000000 || hi!==24'hff0000)
   $fatal(1,"A15-high I/O read must enable the sensed latch alone");
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
            self.assertIn('BUS_SAMPLE 4000 0000 00 0 1 1', result.stdout)
            self.assertIn('BUS_LATCH 4000 00 00', result.stdout)
            self.assertIn('BUS_DRIVE 4000 000000000101101010100101 000000001010010101011010', result.stdout)

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
