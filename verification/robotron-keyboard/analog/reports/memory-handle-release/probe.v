`timescale 1ns/1ps
module test;
 reg [7:0] mem[0:1];
 initial begin
 mem[0]=17;mem[1]=34;
 #1;$memory_handle_release;
 mem[0]=35;mem[1]=70;
 #1;$memory_handle_release;
 #1;$display("CONTINUE %0d %0d",mem[0],mem[1]);$finish;
 end
endmodule
