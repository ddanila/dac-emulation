`timescale 1ns/1ps
module probe;
initial begin
 repeat(5) begin #1; $resolver_drive; end
 #1; $finish;
end
endmodule
