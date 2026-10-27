`timescale 1ns/1ps
module array_probe;
reg [7:0] memory [0:3];
`ifdef ARRAY_AUTO
task automatic unsupported;
 begin end
endtask
`endif
`ifdef ARRAY_TWO
bit [7:0] other [0:3];
`endif
initial begin
 memory[0]=8'ha5;
`ifdef ARRAY_TWO
 other[0]=8'h5a;
`endif
 #1;
`ifdef ARRAY_CALLBACK
 $array_callback;
`endif
 $array_observe;
 $display("CONTINUED %0t",$time);
 $finish;
end
endmodule
