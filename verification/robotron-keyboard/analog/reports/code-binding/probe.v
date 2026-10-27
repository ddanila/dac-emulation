`timescale 1ns/1ps
`define STEP value=value+1;
`define FOUR `STEP `STEP `STEP `STEP
`define SIXTEEN `FOUR `FOUR `FOUR `FOUR
`define SIXTYFOUR `SIXTEEN `SIXTEEN `SIXTEEN `SIXTEEN
`define BLOCK `SIXTYFOUR `SIXTYFOUR `SIXTYFOUR `SIXTYFOUR
module code_binding;
integer value=0;
initial begin
 #1;$thread_observe;
 `BLOCK
 $thread_observe;
 `BLOCK
 $thread_observe;
 $display("VALUE %0t %0d",$time,value);
 #1;$thread_observe;$finish;
end
endmodule
