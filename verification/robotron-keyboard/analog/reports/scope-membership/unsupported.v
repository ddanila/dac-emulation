`timescale 1ns/1ps
module unsupported_scope;
task automatic unused;
 begin end
endtask
initial begin
 #1; $thread_observe;
 $display("CONTINUED %0t", $time);
 $finish;
end
endmodule
