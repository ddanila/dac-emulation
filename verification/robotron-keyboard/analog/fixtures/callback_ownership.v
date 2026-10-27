`timescale 1ns/1ps
module probe;
reg [3:0] a=0;
initial begin
 #1; $ownership_watch;
 #1; a=1;
 #1; $ownership_cancel;
 #1; a=2;
 #1; $finish;
end
endmodule
