`timescale 1ns/1ps
module test;
 reg [3:0] memory[0:1];
 reg select;
 wire [3:0] observed=memory[select];
 initial begin
  select=0;memory[0]=3;memory[1]=10;
  #1;$memory_fault_continue;
  memory[0]=12;memory[1]=5;select=1;
  #1;$index_memory;$memory_fault_continue;
  memory[0]=memory[1]+2;select=0;
  #1;$display("CONTINUE %0d %0d %0d",memory[0],memory[1],observed);$finish;
 end
endmodule
