`timescale 1ns/1ps
module mux_partial_probe;
initial begin
 repeat (10) begin #1; $mux_partial_step; end
 #1; $mux_partial_observe; $finish;
end
endmodule
