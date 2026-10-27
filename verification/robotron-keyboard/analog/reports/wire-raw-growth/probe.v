`timescale 1ns/1ps
module probe;
initial begin #1; $wire_raw_step; #1; $wire_raw_step; #1; $wire_raw_step;
 #1; $finish; end
endmodule
