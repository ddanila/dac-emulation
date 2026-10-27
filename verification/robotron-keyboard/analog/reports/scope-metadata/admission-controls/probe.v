`timescale 1ns/1ps
module leaf; reg [3:0] value=2; endmodule
module test;
 leaf child();
 reg [3:0] value=3;
 initial begin
  #1; $scope_admission;
  #1; value=5; $scope_admission;
  #1; $display("CONTINUE %0d %0d",value,child.value); $finish;
 end
endmodule
