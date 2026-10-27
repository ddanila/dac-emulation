`timescale 1ns/1ps
module signal_family;
reg [7:0] supported=8'h39;
`ifdef FAMILY_AUTOMATIC
 task automatic visit;
 reg [7:0] other;
 begin
  other=8'h5a;#1;
  if(other!==8'h5a || supported!==8'h39)$fatal;
  $display("FAMILY_PRESENT automatic");$family_observe;
  $display("CONTINUED %0t",$time);
 end
 endtask
 initial begin visit;$finish;end
`else
 `ifdef FAMILY_REAL
 real other;
 initial begin
 other=1.5;#1;if(other!=1.5)$fatal;
 $display("FAMILY_PRESENT real");
 `elsif FAMILY_STRING
 string other;
 initial begin
 other="signal";#1;if(other!="signal")$fatal;
 $display("FAMILY_PRESENT string");
 `elsif FAMILY_OBJECT
 int other[];
 initial begin
 other=new[2];other[0]=165;other[1]=90;#1;
 if(other.size()!=2 || other[0]!=165 || other[1]!=90)$fatal;
 $display("FAMILY_PRESENT object");
 `endif
 if(supported!==8'h39)$fatal;
 $family_observe;$display("CONTINUED %0t",$time);$finish;
 end
`endif
endmodule
