`timescale 1ns/1ps
module probe(input clk, output reg sink);
 always @(posedge clk) begin
   sink <= 1'b0;
   $display("EDGE %0t", $time);
 end
endmodule
