`timescale 1ns/1ps
module probe;
initial begin
 #1; $growth_drive; #0; $growth_settle;
 #1; $growth_drive; #0; $growth_settle;
 #1; $growth_drive; #0; $growth_settle;
 #1; $finish;
end
endmodule
