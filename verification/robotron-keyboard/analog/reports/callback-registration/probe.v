`timescale 1ns/1ps
module probe;
reg [3:0] a=0;
initial begin
 #1; $reg_start;
 #1; a=1; #0; $reg_inspect;
 #1; $reg_admit;
 #1; a=2;
 #1; $reg_replace;
 #1; a=3; #0; $reg_inspect;
 #1; $reg_cancel;
 #1; a=4; #0; $reg_inspect;
 #1; $reg_restart;
 #1; a=5; #0; $reg_inspect;
 #1; $finish;
end
endmodule
