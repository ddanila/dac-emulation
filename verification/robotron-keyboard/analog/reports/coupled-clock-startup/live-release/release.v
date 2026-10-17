`timescale 1ns/1ps
module release_probe(input clk, input rst, input [7:0] sense,
 input rx_data, input rx_clock, output dsink, output csink,
 output [1:0] leds, output reg [12:0] columns);
 assign dsink = 1'bx;
 assign csink = 1'bx;
 assign leds = 2'bxx;
 always @(posedge clk) columns <= 13'b0;
endmodule
