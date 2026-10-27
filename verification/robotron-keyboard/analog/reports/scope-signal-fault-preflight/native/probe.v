`timescale 1ns/1ps
module test;
 reg signed [3:0] visible=-6, hidden=-6;
 initial begin
  #1;$scope_signals;
  #1;$scope_signals;
  #1;$display("CONTINUE %0d %0d",visible,hidden);$finish;
 end
endmodule
