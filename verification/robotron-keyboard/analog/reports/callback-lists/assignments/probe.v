`timescale 1ns/1ps
module probe;
initial begin
 $raw_settled;
 repeat(15) begin #1; $raw_drive; #0; $raw_settled; end
 #1; $finish;
end
endmodule
