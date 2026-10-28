`timescale 1ns/1ps
module test;
 reg [3:0] memory[0:1];
 initial begin
  memory[0]=3;memory[1]=10;
  #1;$memory_metadata;
  #1;$memory_metadata;
  #1;$display("CONTINUE %0d %0d",memory[0],memory[1]);$finish;
 end
endmodule
