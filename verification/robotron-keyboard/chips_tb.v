`timescale 1ns/1ps
module chips_tb;
 reg pre1=1, clr1=1, d1=0, clk1=0;
 reg pre2=1, clr2=1, d2=0, clk2=0;
 wire q1,nq1,q2,nq2;
 chip_DL074 dut(.p1(clr1),.p2(d1),.p3(clk1),.p4(pre1),.p5(q1),.p6(nq1),
  .p7(1'b0),.p8(nq2),.p9(q2),.p10(pre2),.p11(clk2),.p12(d2),.p13(clr2),.p14(1'b1));
 reg [7:0] latch_data=0;
 reg stb=0, oe_n=1;
 wire [7:0] latch_out;
 chip_I8282 latch_dut(.p1(latch_data[0]),.p2(latch_data[1]),.p3(latch_data[2]),.p4(latch_data[3]),
  .p5(latch_data[4]),.p6(latch_data[5]),.p7(latch_data[6]),.p8(latch_data[7]),
  .p9(oe_n),.p10(1'b0),.p11(stb),.p20(1'b1),
  .p12(latch_out[7]),.p13(latch_out[6]),.p14(latch_out[5]),.p15(latch_out[4]),
  .p16(latch_out[3]),.p17(latch_out[2]),.p18(latch_out[1]),.p19(latch_out[0]));
 task check_latch;
  input [7:0] expected;
  begin
   #1;
   if(latch_out !== expected)
    $fatal(1,"8282 pin truth table at %0t: actual %b expected %b",$time,latch_out,expected);
  end
 endtask
 task check;
  input [3:0] expected;
  begin
   #1;
   if({q1,nq1,q2,nq2} !== expected)
    $fatal(1,"DL074 pin truth table at %0t: actual %b expected %b",$time,{q1,nq1,q2,nq2},expected);
  end
 endtask
 initial begin
  check(4'bxxxx);
  clr1=0; pre2=0; check(4'b0110);
  clr1=1; pre2=1; check(4'b0110);
  d1=1; d2=0; check(4'b0110); // D alone must not be transparent.
  clk1=1; clk2=1; check(4'b1001);
  d1=0; d2=1; clk1=0; clk2=0; check(4'b1001);
  pre1=0; clr1=0; pre2=0; clr2=0; check(4'b1111);
  pre1=1; clr1=1; pre2=1; clr2=1; check(4'bxxxx);
  clk1=1; clk2=1; check(4'b0110); // A valid clock recovers storage.
  pre1=0; clr1=0; pre2=0; clr2=0; check(4'b1111);
  pre1=1; clr2=1; check(4'b0110); // Release order selects the remaining control.
  clr1=1; pre2=1; check(4'b0110);
  clk1=0; clk2=0; d1=1; d2=0; check(4'b0110);
  clk1=1'bx; clk2=1'bx; check(4'bxxxx); // Ambiguous edges cannot capture known D.
  clk1=0; clk2=0; check(4'bxxxx);
  clk1=1; clk2=1; check(4'b1001);
  clr1=1'bx; pre2=1'bz; check(4'bxxxx);
  clr1=0; pre2=0; check(4'b0110);
  clr1=1; pre2=1; clk1=0; clk2=0; d1=1'bx; d2=1'bz; check(4'b0110);
  clk1=1; clk2=1; check(4'bxxxx); // Driven outputs cannot become high impedance.
  $display("PASS DL074 numbered pins, asynchronous conflict/release, hold and unknown inputs");
  check_latch(8'hzz);
  stb=1; latch_data=8'ha5; check_latch(8'hzz);
  stb=0; oe_n=0; check_latch(8'ha5);
  latch_data=8'h3c; check_latch(8'ha5);
  stb=1; check_latch(8'h3c);
  latch_data=8'h96; check_latch(8'h96);
  oe_n=1; latch_data=8'h0f; check_latch(8'hzz);
  oe_n=0; check_latch(8'h0f);
  stb=1'bx; check_latch(8'h0f);
  latch_data=8'h0e; check_latch(8'b0000111x);
  latch_data=8'hf0; check_latch(8'hxx);
  stb=0; check_latch(8'hxx);
  stb=1; check_latch(8'hf0);
  latch_data=8'b1111zz00; check_latch(8'b1111xx00);
  oe_n=1'bx; check_latch(8'hxx);
  oe_n=1; check_latch(8'hzz);
  oe_n=0; check_latch(8'b1111xx00);
  $display("PASS 8282 numbered pins, transparency, hold, independent output enable and unknown inputs");
  $finish;
 end
endmodule
