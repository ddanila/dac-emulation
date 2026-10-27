`timescale 1ns/1ps
module test;
 reg [3:0] value=3;
 initial begin
  #1; $scope_referents;
  #1; value=5; $display("CONTINUE %0d %.3f",value,$realtime);
  #1; $finish;
 end
endmodule
