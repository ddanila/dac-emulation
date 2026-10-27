`timescale 1ns/1ps
module test;
reg x;
task automatic scope_task;
 begin $scope_admission; end
endtask
initial begin x=1;#1 scope_task;#1 $display("CONTINUE %0d",x);$finish;end
endmodule
