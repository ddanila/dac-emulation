`timescale 1ps/1ps
module probe;
initial begin
 $startup_done;
 #1;
 $finish;
end
endmodule
