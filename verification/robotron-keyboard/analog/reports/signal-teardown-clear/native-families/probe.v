`timescale 1ns/1ps
module test;
reg signed [3:0] r;
wire [0:3] n=r;
integer number;
reg [70:-2] wide;
reg [2:-1] negative;
reg single;
bit [3:0] two;
real real_value;
wire [3:0] netarr [0:1];
assign netarr[0]=r;
assign netarr[1]=negative;
initial begin
 r=10;number=-17;wide=73'h1000000000000000001;negative=6;single=1;two=3;real_value=1.5;
 #1 $handle_families;
 #1 $handle_families;
 #1 $handle_families;
 #1 r=5;number=-33;wide=1;
 #1 $handle_families;
 $display("CONTINUE %0d %0d %0d",r,number,wide);
 $finish;
end
endmodule
