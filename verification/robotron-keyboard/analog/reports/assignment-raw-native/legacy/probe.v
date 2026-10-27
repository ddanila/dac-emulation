`timescale 1ns/1ps
module probe;
reg [79:0] wide=80'h0123456789abcdef0123;
reg [7:0] a=0;
tri [3:0] strengths;
assign (strong1, weak0) strengths=4'b10xz;
wire [79:0] inverted=~wide;
initial $monitor("CHANGE %0t %h %h %b",$time,a,wide,strengths);
initial begin
 a <= #10 8'ha5;
 a[7:4] <= #12 4'hc;
 wide <= #8 80'hfedcba9876543210fedc;
 #1; $assignment_observe;
 $display("VALUES %0t %h %h %h %b",$time,a,wide,inverted,strengths);
 #15; $assignment_observe;
 $display("VALUES %0t %h %h %h %b",$time,a,wide,inverted,strengths);
 #1; $finish;
end
endmodule
