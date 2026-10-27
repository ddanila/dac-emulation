`timescale 1ns/1ps
module probe;
initial begin
 repeat (11) begin #1; $reduction_step; end
 #1; $finish;
end
endmodule
