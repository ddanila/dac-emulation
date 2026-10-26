`timescale 1ns/1ps
module probe;
reg [7:0] value=0;
integer i;
localparam real FRACTION=1.25;
initial begin
 $timeformat(-9, 2, " ns", 8);
 for(i=0;i<3;i=i+1) begin
  #2; value=8'ha0+i; value<=8'hb0+i;
  $strobe("STROBE %0t %h %0.2f", $time, value, FRACTION);
  $display_inventory;
  #1; $display_inventory;
  #7;
 end
 $finish;
end
endmodule
