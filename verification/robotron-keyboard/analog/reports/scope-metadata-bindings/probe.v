`timescale 1ns/1ps
module leaf; reg [3:0] value=2; endmodule
module test;
 leaf child();
 function [7:0] identity(input [7:0] x); identity=x; endfunction
 reg [3:0] value=3;
 initial begin
  #1; $scope_metadata_bindings;
  #1; value=5; $scope_metadata_bindings;
  #1; $display("CONTINUE %0d %0d",value,child.value); $finish;
 end
endmodule
