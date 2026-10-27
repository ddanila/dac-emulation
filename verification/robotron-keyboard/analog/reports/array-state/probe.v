`timescale 1ns/1ps
module array_probe;
reg [7:0] memory [0:3];
reg [79:0] wide [0:1];
reg [2:0] address=0;
wire [7:0] selected=memory[address];
wire [7:0] fixed_word=memory[1];
initial begin
 #1;$array_observe;
 memory[0]=8'ha5;memory[1]=8'hzz;memory[2][7:4]=4'hc;
 wide[0]=80'h123456789abcdef01234;
 #1;$array_observe;
 $array_cache;address=1;
 #1;$array_observe;$display("READ %0t %h %h",$time,selected,fixed_word);
 address=7;
 #1;$array_observe;$display("OUTSIDE %0t %h",$time,selected);
 address=2;
 #1;$array_observe;$display("PARTIAL %0t %h",$time,selected);
 $finish;
end
endmodule
