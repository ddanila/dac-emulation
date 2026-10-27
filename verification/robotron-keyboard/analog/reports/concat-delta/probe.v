`timescale 1ns/1ps
module probe;
initial begin
 repeat (8) begin #1; $concat_step; end
 #1; $finish;
end
endmodule
