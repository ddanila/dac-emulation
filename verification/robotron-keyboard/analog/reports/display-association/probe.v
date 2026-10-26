`timescale 1ns/1ps
module probe;
reg [7:0] first=0, second=0;
integer i;
initial begin
 $timeformat(-9,2," ns",8);
 for(i=0;i<3;i=i+1) begin
  #2; first=8'ha0+i; second=8'hc0+i;
  first<=8'hb0+i; second<=8'hd0+i;
  $strobe("FIRST %0t %h",$time,first);
  $strobe("SECOND %0t %h",$time,second);
  $display_inventory;
  #1; $display_inventory;
  #7;
 end
 $finish;
end
endmodule
