`timescale 1ns/1ps
module probe;
reg enable=0;
reg [3:0] left=4'b1010, right=4'bzzzz;
tri [3:0] a,b;
assign (strong1,strong0) a=left;
assign (weak1,weak0) b=right;
tranif1 bridge[3:0](a,b,enable);
initial $monitor("CHANGE %0t %b %b %b",$time,enable,a,b);
initial begin
 #1; $island_observe;
 enable=1;
 #1; $island_observe;
 right=4'b0101;
 #1; $island_observe;
 enable=1'bx;
 #1; $island_observe;
 left=4'bzzzz;
 #1; $island_observe;
 enable=0;
 #1; $island_observe;
 enable=1;left=4'b1100;
 #1; $island_observe;
 #1; $finish;
end
endmodule
