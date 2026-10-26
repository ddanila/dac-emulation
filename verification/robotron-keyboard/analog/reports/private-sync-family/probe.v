`timescale 1ns/1ps
module probe;
reg clk=0;
reg value=0;
always #5 clk=~clk;
always @(clk or value) $display("VALUE %0t %b %b",$time,clk,value);
initial begin
 value <= #7 1;
 #2; $strobe("STROBE %0t", $time); $queue_inventory;
 #10; $strobe("STROBE %0t", $time); $queue_inventory;
 #10; $strobe("STROBE %0t", $time); $queue_inventory;
 #4; $finish;
end
initial begin
 #1; value <= #8 0;
end
endmodule
