`timescale 1ns/1ps
module mux_growth_probe;
initial begin
 repeat (5) begin #1; $mux_grow_step; end
 $finish;
end
endmodule
