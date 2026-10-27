`timescale 1ns/1ps
module probe;
reg keep=0;
initial begin
 repeat(7) begin #1; $owner_step; end
 #1; $display("KEEP %b",keep); $finish;
end
endmodule
