`timescale 1ns/1ps
module wire_raw_family;
initial begin
 #1; $raw_family_drive;
 #1; $raw_family_drive;
 #1; $finish;
end
endmodule
