`timescale 1ns/1ps
module probe;
reg [3:0] a=0,b=0;
initial begin
 #1; $nest_start;
 #1; a=1; #0; $nest_inspect; $display("VALUES %0t %d %d",$time,a,b);
 #2; a=4; #0; $nest_inspect; $display("VALUES %0t %d %d",$time,a,b);
 #2; b=5; #0; $nest_inspect; $display("VALUES %0t %d %d",$time,a,b);
 #1; $finish;
end
endmodule
