`timescale 1ns/1ps
module wait_unsupported;
reg clk=0;
reg [7:0] value=0;
initial begin
 value <= repeat(3) @(posedge clk) 8'h5a;
 #1 $wait_observe;
 $display("CONTINUED %0t",$time);
end
always #1 clk=~clk;
initial begin
 #7 $display("RESULT %0t %h",$time,value);
 #1 $finish;
end
endmodule
