`timescale 1ns/1ps
// Digital isolation only: no analog voltage, oscillator or reset RC claim.
module service_tb;
 reg oscillator=0,reset_source_n=0,br1_closed=1,br2_closed=1;
 reg external_clk=1'bz,external_reset_n=1'bz;
 wire cpu_clk,cpu_reset_n;
 integer checks=0;
 reg [4095:0] wave;
 controller_service dut(oscillator,reset_source_n,br1_closed,br2_closed,
  external_clk,external_reset_n,cpu_clk,cpu_reset_n);
 task expect_pins(input expected_clk,expected_reset);
 begin
  #1;checks=checks+1;
  if(cpu_clk!==expected_clk || cpu_reset_n!==expected_reset)
   $fatal(1,"SERVICE check=%0d clk=%b/%b reset=%b/%b",checks,cpu_clk,expected_clk,cpu_reset_n,expected_reset);
 end
 endtask
 initial begin
  if(!$value$plusargs("wave=%s",wave))wave="service.vcd";
  $dumpfile(wave);$dumpvars(0,service_tb);
  expect_pins(0,0);
  oscillator=1;reset_source_n=1;expect_pins(1,1);
  // Reset can be held externally while the independent clock keeps running.
  br2_closed=0;external_reset_n=0;expect_pins(1,0);
  oscillator=0;expect_pins(0,0);
  reset_source_n=0;external_reset_n=1;expect_pins(0,1);
  // Both bridges open: onboard sources cannot override external stimulus.
  br1_closed=0;external_clk=1;expect_pins(1,1);
  oscillator=1;external_clk=0;expect_pins(0,1);
  external_reset_n=0;expect_pins(0,0);
  // Open un-driven reset floats. CLK retains its reference R10.3 pullup.
  external_clk=1'bz;external_reset_n=1'bz;expect_pins(1,1'bz);
  // Reconnection restores sources; opposing active drivers must expose X.
  br1_closed=1;br2_closed=1;expect_pins(1,0);
  external_clk=0;expect_pins(1'bx,0);
  external_clk=1'bz;external_reset_n=1;expect_pins(1,1'bx);
  external_reset_n=1'bz;expect_pins(1,0);
  $display("SERVICE checks=%0d mismatches=0",checks);$finish;
 end
endmodule
