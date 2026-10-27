`timescale 1ns/1ps
module probe;
reg [3:0] a=0, b=0;
initial begin
 #1; $value_watch;
 #1; a=1; b=2;
 #1; $value_observe;
 #1; a=3; b=4;
 #1; $value_cancel;
 #1; a=5; b=6;
 #1; $value_retired;
 #1; $value_cancel_head;
 #1; a=7; b=8;
 #1; $value_retired_head;
 #1; $finish;
end
endmodule
