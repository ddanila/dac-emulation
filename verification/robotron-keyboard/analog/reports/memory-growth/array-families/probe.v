`timescale 1ns/1ps
module array_family;
reg [7:0] memory [0:3];
`ifdef FAMILY_REAL
real other [0:3];
`endif
`ifdef FAMILY_STRING
string other [0:3];
`endif
`ifdef FAMILY_NET
wire [7:0] other [0:3];
assign other[0]=memory[0];
`endif
initial begin
 memory[0]=8'ha5;
`ifdef FAMILY_REAL
 other[0]=1.5;
`endif
`ifdef FAMILY_STRING
 other[0]="array";
`endif
 #1;
 $family_check;
 $family_observe;
 $display("CONTINUED %0t",$time);
 $finish;
end
endmodule
