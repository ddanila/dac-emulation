`timescale 1ns/1ps
module test;
reg [3:0] a,b;
initial begin
 a=10;b=3;
 #1 $callback_links;
 #1 a=5;b=12;
 #1 $callback_links;
 #1 a=7;b=1;
 #1 $callback_links;
 $display("CONTINUE %0d %0d",a,b);
 $finish;
end
endmodule
