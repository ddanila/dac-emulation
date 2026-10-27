`timescale 1ns/1ps
module test;
reg signed [3:0] left;
reg [3:0] right;
initial begin
 left=10; right=3;
 #1 $referents;
 #1 left=5;
 #1 $display("CONTINUE %0d %0d",left,right);
 $finish;
end
endmodule
