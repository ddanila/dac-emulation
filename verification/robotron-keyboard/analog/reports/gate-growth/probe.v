`timescale 1ns/1ps
module gate_growth_probe;
initial begin
 repeat (5) begin #1; $gate_step; end
 $finish;
end
endmodule
