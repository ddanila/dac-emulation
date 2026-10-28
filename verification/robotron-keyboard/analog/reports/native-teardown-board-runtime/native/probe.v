`timescale 1ns/1ps
module teardown_leaf #(parameter [79:0] W=80'h123456789abcdef01234,
 parameter real R=2.5, parameter S="G\000R") (input clk, output [7:0] q);
 reg [7:0] memory[0:3];
 reg [1:0] index=0;
 assign q=memory[index];
 initial begin memory[0]=17;memory[1]=34;memory[2]=51;memory[3]=68; end
 always @(posedge clk) index<=index+1;
 initial begin #4;$display("LEAF %m %h %0.1f %h %0d",W,R,S,q);end
endmodule
module test;
 reg clk=0;wire [7:0] a,b;
 teardown_leaf left(clk,a);
 teardown_leaf #(.R(3.5)) right(clk,b);
 always #0.5 clk=~clk;
 initial begin $monitor("MONITOR %0t %0d %0d",$time,a,b);#5;$display("CONTINUE %0d %0d",a,b);$finish;end
endmodule
