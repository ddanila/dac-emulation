`timescale 1ns/1ps
module net_probe;
reg [7:0] source=8'h12;
reg [7:0] forced=8'ha5;
reg [7:0] unused=8'h39;
wire [7:0] a=source^8'h5a;
wire [7:0] b=source+8'h01;
wire [63:0] wide={source,a,b,source,a,b,source,a};
initial begin
 #1;$net_observe;$display("VALUE %0t %h %h %h",$time,a,b,wide);
 force a=forced;
 #1;$net_observe;$display("VALUE %0t %h %h %h",$time,a,b,wide);
 source=8'h34;forced=8'hc3;
 #1;$net_observe;$display("VALUE %0t %h %h %h",$time,a,b,wide);
 release a;
 #1;$net_observe;$display("VALUE %0t %h %h %h",$time,a,b,wide);
 force a=forced;
 #1;$net_observe;$display("VALUE %0t %h %h %h",$time,a,b,wide);
 release a;
 #1;$net_observe;$display("VALUE %0t %h %h %h",$time,a,b,wide);
 $finish;
end
endmodule
