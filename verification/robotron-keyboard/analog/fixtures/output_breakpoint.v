`timescale 1ns/1ps
module delayed_output(input wire unused_input,output reg q);
initial begin
 q=0;
 #53 q=1; $display("PROBE_EDGE %0t %b",$time,q);
 #78 q=0; $display("PROBE_EDGE %0t %b",$time,q);
 #66 q=1; $display("PROBE_EDGE %0t %b",$time,q);
 #104 q=0; $display("PROBE_EDGE %0t %b",$time,q);
end
endmodule
