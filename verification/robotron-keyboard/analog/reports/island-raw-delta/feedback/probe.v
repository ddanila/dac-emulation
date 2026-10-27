`timescale 1ns/1ps
module probe;
initial begin
 repeat(10) begin #1; $growth_drive; #0; $growth_settle; end
 #1; $finish;
end
endmodule
