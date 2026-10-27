`timescale 1ns/1ps
module probe;
reg [3:0] a=0;
initial begin
 #1; $list_watch;
 #1; a=1;
 #1; $list_cancel_middle;
 #1; a=2; #0; $list_inspect;
 #1; $list_cancel_head;
 #1; a=3; #0; $list_inspect;
 #1; $list_cancel_tail;
 #1; a=4; #0; $list_inspect;
 #1; $finish;
end
endmodule
