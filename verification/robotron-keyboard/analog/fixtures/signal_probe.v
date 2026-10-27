`timescale 1ns/1ps
module signal_probe;
reg [7:0] source=8'h12;
reg [7:0] other=8'hc3;
reg [7:0] target;
reg [79:0] wide;
reg [7:0] unwritten;
task show;
begin $signal_observe; $display("VALUE %0t %h %h %h",$time,target,wide,unwritten); end
endtask
initial begin
 show;
 #1;target=8'h5a;wide=80'h0123456789abcdef0123;show;
 assign target=source;
 #1;show;
 source=8'h34;target=8'hff;
 #1;show;
 assign target=other;source=8'h87;
 #1;show;
 deassign target;target=8'h96;
 #1;show;
 assign target[3:0]=4'ha;
 #1;show;
 target=8'h55;
 #1;show;
 deassign target[1:0];target=8'h03;
 #1;show;
 deassign target[3:2];target=8'hxz;wide=80'hxz0123456789abcdefxz;
 #1;show;
 force target=source;target=8'ha5;
 #1;show;
 release target;target=8'h72;
 #1;show;
 $finish;
end
endmodule
