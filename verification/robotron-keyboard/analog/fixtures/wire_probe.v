`timescale 1ns/1ps
module wire_probe;
reg [7:0] source=8'h12;
reg [7:0] forced=8'ha5;
reg [7:0] unused=8'h39;
wire [7:0] a=source^8'h5a;
wire [7:0] b=source+8'h01;
wire [63:0] wide={source,a,b,source,a,b,source,a};
tri [7:0] c,d;
assign (strong1,strong0) c=source;
tran bridge[7:0](c,d);
wire [79:0] widewire={10{source}};
wire [79:0] wideforced={10{forced}};
initial begin
 #1;$wire_observe;$display("VALUE %0t %h %h %h",$time,a,b,wide);
 force a=forced;force c=forced;force widewire=wideforced;
 #1;$wire_observe;$display("VALUE %0t %h %h %h",$time,a,b,wide);
 source=8'h34;forced=8'hc3;
 #1;$wire_observe;$display("VALUE %0t %h %h %h",$time,a,b,wide);
 release a;release c;release widewire;
 #1;$wire_observe;$display("VALUE %0t %h %h %h",$time,a,b,wide);
 force a=forced;force c=forced;force widewire=wideforced;
 #1;$wire_observe;$display("VALUE %0t %h %h %h",$time,a,b,wide);
 release a;release c;release widewire;
 #1;$wire_observe;$display("VALUE %0t %h %h %h",$time,a,b,wide);
 $finish;
end
endmodule
