`timescale 1ns/1ps
module probe;
initial begin
 #1; $native_drive; #0; $native_settled;
 #1; $finish;
end
endmodule
