`timescale 1ns/1ps
module test;
 reg [7:0] memory[0:1];
 initial begin
 memory[0]=17;memory[1]=34;
 #1;$memory_lifecycle;
 #1;$memory_lifecycle;
 #1;$display("CONTINUE %0d %0d",memory[0],memory[1]);$finish;
 end
endmodule
