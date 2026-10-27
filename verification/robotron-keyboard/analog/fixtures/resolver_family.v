`timescale 1ns/1ps
module probe;
initial begin
 #1; $resolver_family_drive;
 #1; $resolver_family_drive;
 #1; $finish;
end
endmodule
