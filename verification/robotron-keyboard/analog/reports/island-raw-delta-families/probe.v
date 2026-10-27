`timescale 1ns/1ps
module probe;
initial begin
 #1; $family_drive; #0; $family_settle;
 #1; $family_drive; #0; $family_settle;
 #1; $finish;
end
endmodule
