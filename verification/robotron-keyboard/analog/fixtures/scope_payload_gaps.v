`timescale 1ns/1ps
module test;
 parameter [3:0] P=3;
 reg signed [3:0] visible=-6, hidden=-6;
 reg [7:0] memory [0:1];
 initial begin
  memory[0]=5;memory[1]=7;
  #1;$scope_payload_gaps;
  #1;$scope_payload_gaps;
  #1;$display("CONTINUE %0d %0d %0d %0d",visible,hidden,P,memory[0]);$finish;
 end
endmodule
