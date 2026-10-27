`timescale 1ns/1ps
module probe;
initial begin
 repeat(13) begin #1; $resolver_drive; end
 #1; $finish;
end
endmodule
