`timescale 1ns/1ps
module wait_probe;
reg clk=0,a=0,b=0;
reg [79:0] bus=0;
event pulse;
real rv=0.0;
string sv="";
always @(rv) $display("REAL %0t %g",$time,rv);
always @(sv) $display("STRING %0t %s",$time,sv);
always @(posedge a or negedge b) $display("MIXED %0t",$time);
always @(posedge clk) $display("RISE %0t",$time);
always @(negedge clk) $display("FALL %0t",$time);
always @(a or b) $display("OR %0t %b%b",$time,a,b);
always @(bus) $display("BUS %0t %h",$time,bus);
initial begin @pulse; $display("NAMED %0t",$time); end
task automatic worker(input integer id);
 reg local_clock;
 event local_pulse;
 begin
  local_clock=0;
  fork
   begin #2 local_clock=1; #2 ->local_pulse; end
   begin @(posedge local_clock or local_pulse); $display("AUTO_OR %0t %0d",$time,id); end
   begin @(local_clock); $display("AUTO_ANY %0t %0d",$time,id); end
   begin @(posedge local_clock); $display("AUTO_EDGE %0t %0d",$time,id);
         @local_pulse; $display("AUTO_NAMED %0t %0d",$time,id); end
  join
 end
endtask
initial begin fork worker(1);worker(2);join end
initial begin
 #1 $wait_observe;
 #1 clk=1;a=1;rv=1.25;sv="kept";bus=80'hffffffffffffffffffff;
 #1 $wait_observe;
 #1 clk=0;b=1;->pulse;
 #1 $wait_observe;
 #1 clk=1;bus=80'h123456789abcdef01234;
 #1 $wait_observe;
 #1 $finish;
end
endmodule
