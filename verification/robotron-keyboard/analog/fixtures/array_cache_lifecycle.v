`timescale 1ns/1ps
module test;
 initial begin
  #1;$array_cache_lifecycle;
  #1;$array_cache_lifecycle;
  #1;$display("CONTINUE 1");$finish;
 end
endmodule
