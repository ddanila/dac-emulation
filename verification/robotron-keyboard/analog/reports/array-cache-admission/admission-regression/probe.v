`timescale 1ns/1ps
module test;
 reg [3:0] memory[0:1];
 reg [79:0] wide[0:1];
 initial begin
  memory[0]=3;memory[1]=10;wide[0]=3;
  #1;$array_admission;
  #1;wide[1]=80'h10000000000000000002;$array_admission;
  #1;$display("CONTINUE %0d %0d %h %h",memory[0],memory[1],wide[0],wide[1]);$finish;
 end
endmodule
