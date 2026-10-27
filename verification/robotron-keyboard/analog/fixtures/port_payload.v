`timescale 1ns/1ps
module leaf(input [3:0] a, output [3:0] b); assign b=a; endmodule
module test;
 reg [3:0] value=3;
 wire [3:0] result;
 leaf child(value,result);
 initial begin
  #1; $port_payload;
  #1; value=5; #0; $port_payload;
  #1; $display("CONTINUE %0d %0d",value,result); $finish;
 end
endmodule
