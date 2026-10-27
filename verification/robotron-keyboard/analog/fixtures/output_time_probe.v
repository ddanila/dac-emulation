`timescale 1ps/1ps
module output_time_probe #(parameter KIND=0, parameter EVENT_TICK=10000)
(input signal_in, output reg echo=0);
generate
 if (KIND==0) initial #EVENT_TICK echo=1;
 if (KIND==1) initial #EVENT_TICK echo<=1;
 if (KIND==2) always @(signal_in) echo=signal_in;
 if (KIND==3) always @(signal_in) echo<=signal_in;
endgenerate
always @(posedge echo) $display("OUTPUT_TICK %0t",$time);
endmodule
