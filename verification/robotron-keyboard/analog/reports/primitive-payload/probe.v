`timescale 1ns/1ps
module probe;
reg [79:0] wide=80'h0123456789abcdef0123;
wire [79:0] inverted=~wide;
wire [7:0] selected=wide[11:4];
initial $monitor("CHANGE %0t %h %h %h",$time,wide,inverted,selected);
initial begin
 #1; $primitive_drive;
 #1; $primitive_observe;
 #1; $primitive_drive;
 #1; $primitive_observe;
 #1; $finish;
end
endmodule
