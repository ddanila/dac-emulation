`timescale 1ns/1ps
module probe;
reg [3:0] left=4'b1010;
reg [3:0] forced=4'b0101;
tri [3:0] a,b;
assign (strong1,strong0) a=left;
tranif1 bridge[3:0](a,b,1'b1);
initial $monitor("CHANGE %0t %b %b",$time,a,b);
initial begin
 #1; $filter_observe;
 force a=4'b0011;
 #1; $filter_observe;
 force a[1:0]=2'b10;
 #1; $filter_observe;
 release a[0];
 #1; $filter_observe;
 force a=forced;
 #1; $filter_observe;
 forced=4'b1100;
 #1; $filter_observe;
 release a;
 #1; $filter_observe;
 force a=forced;
 #1; $filter_observe;
 release a;
 #1; $filter_observe;
 #1; $finish;
end
endmodule
