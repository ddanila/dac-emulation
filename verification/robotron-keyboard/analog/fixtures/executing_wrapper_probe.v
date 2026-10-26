`timescale 1ns/1ps
module probe;
initial begin
 #2; $wrapper_schedule;
 #4; $wrapper_empty;
 #6; $wrapper_schedule;
 #4; $wrapper_empty;
 #6; $wrapper_schedule;
 #4; $wrapper_empty;
 #1; $finish;
end
endmodule
