`timescale 1ns/1ps
module gate_input_probe;
initial begin
 repeat (10) begin #1; $gate_step; end
 $finish;
end
endmodule
