`timescale 1ns/1ps
module lifecycle;
scope_empty empty();
initial begin
 fork
  begin #2;$display("CHILD_A %0t",$time);end
  begin #4;$display("CHILD_B %0t",$time);end
 join_none
 #1;$thread_observe;$lifecycle_defer;
 wait fork;
 #1;$thread_observe;
 fork
  begin #5;$display("UNEXPECTED_A");end
  begin #10;$display("UNEXPECTED_B");end
 join_none
 #1;$thread_observe;
 disable fork;
 $thread_observe;
 #11;$thread_observe;
 $display("FINISHED %0t",$time);$finish;
end
initial begin #2;$lifecycle_defer;end
endmodule

module scope_empty;
endmodule
