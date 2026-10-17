`timescale 1ns/1ps
module chips_tb;
 reg pre1=1, clr1=1, d1=0, clk1=0;
 reg pre2=1, clr2=1, d2=0, clk2=0;
 wire q1,nq1,q2,nq2;
 chip_DL074 dut(.p1(clr1),.p2(d1),.p3(clk1),.p4(pre1),.p5(q1),.p6(nq1),
  .p7(1'b0),.p8(nq2),.p9(q2),.p10(pre2),.p11(clk2),.p12(d2),.p13(clr2),.p14(1'b1));
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
  $finish;
 end
endmodule
