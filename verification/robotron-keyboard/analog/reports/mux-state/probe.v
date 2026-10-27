`timescale 1ns/1ps
module mux_probe;
reg [7:0] a=8'h12,b=8'h34;
reg sel=0;
reg [79:0] widea=80'h0123456789abcdef0123;
reg [79:0] wideb=80'hfedcba98765432100123;
wire [7:0] out=sel?b:a;
wire [79:0] wide=sel?wideb:widea;
task show;
begin $mux_observe;$display("VALUE %0t %h %h",$time,out,wide);end
endtask
initial begin
 #1;show;$mux_drive;
 #1;show;sel=1;$mux_observe;
 #1;show;sel=1'bx;$mux_observe;
 #1;show;sel=1'bz;a[3:0]=b[3:0];widea[7:0]=8'hzz;wideb[7:0]=8'hzz;$mux_observe;
 #1;show;sel=0;$mux_observe;
 #1;show;a=a;b=b;$mux_observe;
 #1;show;$finish;
end
endmodule
