`timescale 1ns/1ps
module test;
 parameter [3:0] P=3;
 parameter [79:0] W=80'h123456789abcdef01234;
 parameter real R=1.5;
 parameter S="A\000B";
 initial begin
  #1;$parameter_lifecycle;
  #1;$parameter_lifecycle;
  #1;$display("CONTINUE %0d %h %0.1f",P,W,R);$finish;
 end
endmodule
