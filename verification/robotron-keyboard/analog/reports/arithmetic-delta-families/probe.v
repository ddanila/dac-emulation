`timescale 1ns/1ps
module gate_family;
initial begin
 #1; $arithmetic_family_drive;
 #1; $finish;
end
endmodule
