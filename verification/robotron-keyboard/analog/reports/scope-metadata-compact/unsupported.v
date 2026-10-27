`timescale 1ns/1ps
module test;
 task automatic local_task; reg value; begin value=1; end endtask
 initial begin local_task; #1; $scope_metadata_refuse; $display("CONTINUE automatic"); $finish; end
endmodule
